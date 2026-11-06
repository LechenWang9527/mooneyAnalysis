# -*- coding: utf-8 -*-
"""第 2 步：核心统计。配方内 Spearman（样本量>=20 加权、bootstrap 区间）+ 首末配对差分。

输入：output/masterbatch_mooney_wide_pallet.csv
输出：output/tab_corr.csv、output/tab_paired.csv、output/summary.md
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

W = config.OUT / "masterbatch_mooney_wide_pallet.csv"
if not W.exists():
    raise SystemExit(f"先跑 build_wide.py，没找到 {W}")

df = pd.read_csv(W)
FEATS = ["mb_act_mean", "mb_tgt_mean", "dev_mean", "dev_abs_max", "n_lots_mean",
         "n_mb_materials", "batch_weight_mean", "mix_time_mean", "cycle_time_mean", "n_batches"]
FEATS = [f for f in FEATS if f in df.columns]
rng = np.random.default_rng(42)

def within_corr(d, feat, y="mooney", min_n=20, B=1000):
    rows = []
    for comp, g in d.groupby("compound"):
        g = g[[feat, y]].dropna()
        if len(g) < min_n or g[feat].nunique() < 3:
            continue
        rho = spearmanr(g[feat], g[y]).correlation
        if np.isfinite(rho):
            rows.append((comp, len(g), rho))
    if not rows:
        return None
    comps = [r[0] for r in rows]
    ns = np.array([r[1] for r in rows], dtype=float)
    rhos = np.array([r[2] for r in rows], dtype=float)
    overall = float(np.sum(ns * rhos) / np.sum(ns))
    boots = []
    for _ in range(B):
        idx = rng.integers(0, len(rows), len(rows))
        boots.append(float(np.sum(ns[idx] * rhos[idx]) / np.sum(ns[idx])))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return overall, lo, hi, len(rows)

res = []
for f in FEATS:
    out = within_corr(df, f)
    if out:
        res.append({"feature": f, "rho": round(out[0], 4),
                    "ci_lo": round(out[1], 4), "ci_hi": round(out[2], 4),
                    "n_compounds": out[3]})
tab = pd.DataFrame(res).dropna().sort_values("rho", key=lambda s: s.abs(), ascending=False)
tab.to_csv(config.OUT / "tab_corr.csv", index=False, encoding="utf-8-sig")
print(tab.to_string(index=False))

# 首末配对：同一订单取第一车与最后一车
sub = df[df.sample_pos.isin(["first", "last"])].sort_values(["order_id", "pallet_no"])
pairs = []
for oid, g in sub.groupby("order_id"):
    if len(g) < 2:
        continue
    first, last = g.iloc[0], g.iloc[-1]
    row = {"order_id": oid, "d_mooney": last.mooney - first.mooney}
    for f in FEATS:
        if pd.notna(first[f]) and pd.notna(last[f]):
            row["d_" + f] = last[f] - first[f]
    pairs.append(row)
P = pd.DataFrame(pairs)
prow = []
for f in FEATS:
    col = "d_" + f
    if col in P:
        g = P[[col, "d_mooney"]].dropna()
        if len(g) > 100:
            r = spearmanr(g[col], g.d_mooney).correlation
            prow.append({"feature": f, "paired_rho": round(float(r), 4), "n_pairs": len(g)})
if prow:
    pt = pd.DataFrame(prow).dropna().sort_values("paired_rho", key=lambda s: s.abs(), ascending=False)
    pt.to_csv(config.OUT / "tab_paired.csv", index=False, encoding="utf-8-sig")
    print(pt.to_string(index=False))
else:
    pt = pd.DataFrame()

def md_table(d):
    cols = list(d.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in d.iterrows():
        out.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(out)

lines = ["# 核心结果（自动生成）", "",
         f"样本 {len(df):,} 托盘，{df.order_id.nunique():,} 订单，{df.compound.nunique()} 配方。", "",
         "## 配方内 Spearman", "", md_table(tab)]
if len(pt):
    lines += ["", "## 首末配对差分", "", md_table(pt)]
lines += ["", "注：区间为配方重抽样 bootstrap，仅作快速参考；正式结果见 report/。"]
(config.OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
print("done")


