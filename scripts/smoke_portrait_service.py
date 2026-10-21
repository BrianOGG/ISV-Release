#!/usr/bin/env python3
"""对已启动的本地服务做一轮冒烟测试，确认打包产物真的能用。

这个脚本是发布包「能不能用」的最后一道闸。之前 Windows 包虽然构建成功，却因为
``os.fchmod`` 只存在于 Unix 而在「配置账号密码」时直接返回 HTTP 500——服务能启动
并不代表功能可用。冒烟测试会实际调用写本地文件的那几个接口，任何 5xx 都判为失败。

检查项：

1. 首页可访问。
2. ``/api/runtime`` 返回运行信息。
3. 保存一条临时账号配置（会写 accounts.json）。
4. 读回账号配置。
5. 提交一个无效 Cookie 的会话（应返回 4xx 而不是 5xx）。
6. 删除刚才的临时账号配置。

用法：

    python3 scripts/smoke_test_service.py --base-url http://127.0.0.1:8766
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


class CheckFailure(Exception):
    """某一项检查没有通过。"""


def _request(method: str, url: str, payload: dict | None = None,
             timeout: int = 30) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _expect_ok(method: str, url: str, payload: dict | None = None) -> str:
    status, body = _request(method, url, payload)
    if status >= 500:
        raise CheckFailure(f"{method} {url} 返回 {status}（服务端错误）：{body[:300]}")
    if status >= 400:
        raise CheckFailure(f"{method} {url} 返回 {status}（预期成功）：{body[:300]}")
    return body


def _expect_client_error(method: str, url: str, payload: dict | None = None) -> None:
    status, body = _request(method, url, payload)
    if status >= 500:
        raise CheckFailure(f"{method} {url} 返回 {status}（服务端错误）：{body[:300]}")
    if status < 400:
        raise CheckFailure(f"{method} {url} 返回 {status}（预期 4xx）：{body[:300]}")


def _wait_until_ready(base_url: str, timeout: int) -> str:
    """等服务真正起来：打包产物启动要几秒到几十秒。"""
    deadline = time.monotonic() + timeout
    last = "服务没有响应"
    while time.monotonic() < deadline:
        try:
            status, body = _request("GET", f"{base_url.rstrip('/')}/api/runtime", timeout=5)
            if status == 200:
                return body
            last = f"/api/runtime 返回 {status}：{body[:200]}"
        except (urllib.error.URLError, OSError) as error:
            last = f"{type(error).__name__}: {error}"
        time.sleep(1)
    raise CheckFailure(f"等待服务就绪超时（{timeout} 秒）。最后一次结果：{last}")


def run_checks(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    passed: list[str] = []

    body = _expect_ok("GET", f"{base}/")
    if "<html" not in body.lower() and "<!doctype" not in body.lower():
        raise CheckFailure("首页返回的不是 HTML 页面")
    passed.append("首页可访问")

    body = _expect_ok("GET", f"{base}/api/runtime")
    runtime = json.loads(body)
    if not runtime.get("pid"):
        raise CheckFailure(f"/api/runtime 没有返回进程号：{body[:200]}")
    passed.append(f"/api/runtime 正常（storage={runtime.get('storage')} pid={runtime.get('pid')}）")

    account = {"platform": "dmp", "name": "冒烟测试账号",
               "username": "smoke-test@example.invalid", "password": "smoke-test-password"}
    body = _expect_ok("POST", f"{base}/api/auth/accounts", account)
    account_id = json.loads(body)["item"]["id"]
    passed.append("保存账号配置（写 accounts.json）")

    body = _expect_ok("GET", f"{base}/api/auth/accounts?platform=dmp")
    items = json.loads(body)["items"]
    if not any(entry["id"] == account_id for entry in items):
        raise CheckFailure("刚保存的账号配置没有读回来")
    passed.append("读回账号配置")

    _expect_client_error("POST", f"{base}/api/session",
                          {"platform": "dmp", "cookie": "smoke-test-invalid-cookie"})
    passed.append("提交无效 Cookie 返回 4xx（不是 5xx）")

    _expect_ok("DELETE", f"{base}/api/auth/accounts/{account_id}?platform=dmp")
    passed.append("删除账号配置")

    return passed


def main(argv: list[str] | None = None) -> int:
    # Windows runners may inherit a legacy code page such as cp1252. Keep
    # localized diagnostics readable and prevent successful checks from
    # failing while writing their summaries.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    parser.add_argument("--wait-seconds", type=int, default=90,
                        help="等待服务就绪的最长秒数，默认 90")
    arguments = parser.parse_args(argv)

    try:
        _wait_until_ready(arguments.base_url, arguments.wait_seconds)
        passed = run_checks(arguments.base_url)
    except CheckFailure as failure:
        print(f"冒烟测试失败：{failure}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as error:
        print(f"冒烟测试失败：连不上 {arguments.base_url}（{type(error).__name__}: {error}）", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"冒烟测试失败：响应不是合法 JSON（{error}）", file=sys.stderr)
        return 1

    for item in passed:
        print(f"  OK  {item}")
    print(f"冒烟测试通过，共 {len(passed)} 项。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
