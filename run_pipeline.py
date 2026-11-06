# -*- coding: utf-8 -*-
"""一键跑：python run_pipeline.py [wide|analyze|prod|all]"""
import argparse, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

def run(script, optional=False):
    print(f"\n=== {script} ===", flush=True)
    r = subprocess.run([sys.executable, str(BASE / "src" / script)])
    if r.returncode != 0 and not optional:
        raise SystemExit(f"{script} 失败，退出码 {r.returncode}")

p = argparse.ArgumentParser()
p.add_argument("step", nargs="?", default="all", choices=["wide", "analyze", "prod", "all"])
a = p.parse_args()

if a.step in ("wide", "all"):
    run("build_wide.py")
if a.step in ("prod", "all"):
    run("build_prod.py", optional=True)
if a.step in ("analyze", "all"):
    run("analyze.py")

