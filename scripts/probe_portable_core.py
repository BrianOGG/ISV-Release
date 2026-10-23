#!/usr/bin/env python3
"""Offline diagnostic: safe fixed codes, never publish private source or traceback."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

def check(name,callback):
    try:
        return callback()
    except BaseException as error:
        kind=type(error).__name__
        code=str(error) if re.fullmatch("[A-Z_]{3,70}",str(error)) else "REDACTED"
        print("PORTABLE_DIAG="+name+"_"+kind+"_"+code)
        raise SystemExit(1) from None

p=argparse.ArgumentParser()
p.add_argument("--launcher",type=Path,required=True)
p.add_argument("--core",type=Path,required=True)
a=p.parse_args()
spec=importlib.util.spec_from_file_location("ecai_diag_launcher",a.launcher)
mod=importlib.util.module_from_spec(spec)
check("PUBLIC_LAUNCHER_LOAD",lambda:spec.loader.exec_module(mod))
check("CPYTHON_ENV",lambda:mod.check_python(require_venv=True))
check("PRIVATE_CORE_INVENTORY",lambda:mod.verify_release(a.core))
entry=check("PRIVATE_CORE_IMPORT",lambda:mod.load_entry(a.core))
print("PORTABLE_DIAG=PRIVATE_CORE_IMPORT_OK")
code=check("PRIVATE_ENTRY_VERSION",lambda:entry(["version"]))
if code == 0:
    print("PORTABLE_DIAG=PRIVATE_ENTRY_VERSION_OK")
else:
    print("PORTABLE_DIAG=PRIVATE_ENTRY_VERSION_RETURN_NONZERO")
    package="backend._build_resources" if a.core.joinpath("core-build.json").is_file() and __import__("json").loads(a.core.joinpath("core-build.json").read_text()).get("project")=="kol-selection" else "_build_resources"
    try:
        resources=__import__(package,fromlist=["VERSION"])
        value=getattr(resources,"VERSION",None)
        print("PORTABLE_DIAG=VERSION_RESOURCE_FOUND" if isinstance(value,str) else "PORTABLE_DIAG=VERSION_RESOURCE_MISSING")
    except BaseException as err:
        print("PORTABLE_DIAG=VERSION_RESOURCE_"+type(err).__name__)
    raise SystemExit(1)
