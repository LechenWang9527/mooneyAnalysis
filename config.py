# -*- coding: utf-8 -*-
"""路径配置。数据目录默认 ./data，可用环境变量覆盖：MB_DATA_DIR / MB_OUT_DIR。"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MB_DATA_DIR", BASE / "data"))
OUT = Path(os.environ.get("MB_OUT_DIR", BASE / "output"))
OUT.mkdir(parents=True, exist_ok=True)

BM = DATA / "BatchMaterials.csv"
BH = DATA / "BatchHeader.csv"

def datamart() -> Path:
    """门尼检测表。默认找 datamart.csv，找不到就找名字里带 datamart 的第一个。"""
    p = DATA / "datamart.csv"
    if p.exists():
        return p
    cand = sorted(DATA.glob("*datamart*.csv"), key=lambda p: p.stat().st_size, reverse=True)
    if not cand:
        raise FileNotFoundError(f"没找到门尼表，请把 datamart 相关 CSV 放到 {DATA}")
    return cand[0]

def check(files):
    missing = [str(f) for f in files if not Path(f).exists()]
    if missing:
        raise SystemExit("缺少输入文件：\n  " + "\n  ".join(missing))

