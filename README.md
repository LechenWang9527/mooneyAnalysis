# 母胶特征与终炼门尼分析：管线骨架

从三张生产表构建托盘级门尼宽表、做配方内相关与首末配对的独立代码。仓库只含通用管线代码，不含任何生产数据、分析结果或项目报告。

## 目录

```
├─ config.py            路径配置（环境变量可覆盖）
├─ run_pipeline.py      一键执行
├─ src/
│  ├─ build_wide.py     构建门尼宽表
│  ├─ analyze.py        配方内 Spearman 与首末配对
│  └─ build_prod.py     生产侧特征（可选）
├─ data/                放原始 CSV（空）
└─ output/              输出（空）
```

## 需要的数据

| 文件 | 说明 |
|---|---|
| `BatchMaterials.csv` | 母胶投料明细 |
| `BatchHeader.csv` | 车次档案（PalletID、批重、混炼时间等） |
| `datamart*.csv` | 门尼检测记录 |

可选：`BatchData_batch_agg.csv`、`lot_batch_detail.csv`（跑生产特征时才要）。

放 `data/` 下，或设 `MB_DATA_DIR`；输出用 `MB_OUT_DIR`。

## 运行

```bash
pip install -r requirements.txt
python run_pipeline.py all      # 或 wide / analyze / prod
```

## 主要口径

- 母胶：MaterialName 匹配 `^(M[0-9]|M3B|R1)-`，每车次取 ActualWeight 最大的原材料。
- ActualWeight 在批次行里重复，取 max，不能求和；分摊量用 EffectiveConsumedWeight。
- 托盘与车次不是尾号对齐，必须用 BatchHeader.PalletID 关联。
- 门尼保留 L01/L02/L04/R01/R02/C02，剔除 2026-11，复测取最新。
- 生产特征按 EffectiveConsumedWeight 加权聚合。

## 环境

Python 3.10+、DuckDB 1.2+；全量跑第 1 步约 1~3 分钟，建议 8 GB 内存以上。
