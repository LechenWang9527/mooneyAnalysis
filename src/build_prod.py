# -*- coding: utf-8 -*-
"""第 3 步（可选）：生产侧特征并入宽表。

额外输入（放 data/ 下）：
  BatchData_batch_agg.csv   车次过程数据聚合（温度/转速/扭矩/能耗/RAM）
  lot_batch_detail.csv      母胶批次明细（含生产日期、领用时间、消耗量）

输出：output/masterbatch_mooney_wide_pallet_prod.csv
"""
import sys, time
from pathlib import Path
import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

W = config.OUT / "masterbatch_mooney_wide_pallet.csv"
BD = config.DATA / "BatchData_batch_agg.csv"
LOT = config.DATA / "lot_batch_detail.csv"
if not W.exists():
    raise SystemExit("先跑 build_wide.py")
if not BD.exists():
    raise SystemExit(f"缺少 {BD}，跳过生产特征。")
if not LOT.exists():
    raise SystemExit(f"缺少 {LOT}，跳过生产特征。")

t0 = time.time()
con = duckdb.connect()
con.execute("SET threads=6; SET memory_limit='8GB'; SET preserve_insertion_order=false")

con.execute(f"""create view bh as
select OrderID, BatchNumber, BatchWeight, BatchStartTime, BatchCycleTimeSeconds,
       MixingTimeSeconds, ShiftNumber, EquipmentID, PalletID
from read_csv_auto('{config.BH}', types={{'OrderID':'VARCHAR','PalletID':'VARCHAR'}}, nullstr='NULL')""")
con.execute(f"""create view bd as
select OrderID, BatchNumber,
       try_cast(max_batch_temp as double) mt, try_cast(avg_rpm as double) rpm,
       try_cast(max_torque as double) tq, try_cast(energy_kwh as double) en,
       try_cast(max_ram as double) ram
from read_csv_auto('{BD}', types={{'OrderID':'VARCHAR'}})""")
con.execute(f"""create table bm1 as
select OrderID, BatchNumber, EquipmentID, SequenceNumber, MaterialCode,
       max(MaterialName) mname,
       max(try_cast(TargetWeight as double)) t,
       max(try_cast(ActualWeight as double)) a
from read_csv_auto('{config.BM}', types={{'OrderID':'VARCHAR'}})
group by all""")
con.execute("""create table bm_agg as
select OrderID, BatchNumber,
       count(distinct MaterialCode || '/' || SequenceNumber) n_materials,
       sum(t) sum_target, sum(a) sum_actual,
       sum(abs(a - t)) dev_sum, max(abs(a - t)) dev_max,
       sum(case when regexp_matches(mname,'^(M[0-9]|M3B|R1)-') then a else 0 end)
         / nullif(sum(a),0) mb_ratio
from bm1 group by 1,2""")

con.execute("""create table prod as
select h.OrderID, h.BatchNumber, h.PalletID, h.EquipmentID, h.ShiftNumber,
       h.BatchWeight, h.BatchStartTime, h.BatchEndTime,
       h.MixingTimeSeconds mix_s, h.BatchCycleTimeSeconds cycle_s,
       m.n_materials, m.sum_target, m.sum_actual, m.dev_sum, m.dev_max, m.mb_ratio,
       case when b.mt > 400 or b.mt <= 0 then null else b.mt end max_temp,
       b.rpm, case when b.tq < 0 then null else b.tq end max_torque,
       b.en energy_kwh, b.ram max_ram,
       case when b.OrderID is null then 0 else 1 end has_proc
from bh h
left join bm_agg m on h.OrderID = m.OrderID and h.BatchNumber = m.BatchNumber
left join bd b on h.OrderID = b.OrderID and h.BatchNumber = b.BatchNumber""")

con.execute(f"""create table lmap as
select l.order_id, l.pallet_id, l.charge_id, l.effective_consumed_weight w,
       l.lot_first_use_ts, l.original_production_date, l.date_valid,
       p.OrderID p_oid, p.BatchNumber p_bno, p.BatchStartTime p_start,
       p.mix_s, p.cycle_s, p.BatchWeight p_bw, p.ShiftNumber p_shift, p.EquipmentID p_eq,
       p.n_materials, p.sum_target, p.sum_actual, p.dev_sum, p.dev_max, p.mb_ratio,
       p.max_temp, p.rpm, p.max_torque, p.energy_kwh, p.max_ram,
       case when p.OrderID is null then 0 else 1 end is_matched,
       datediff('second', p.BatchStartTime, l.lot_first_use_ts)/3600.0 storage_h
from read_csv_auto('{LOT}') l
left join prod p
  on p.OrderID = left(l.charge_id, 7)
 and p.BatchNumber = try_cast(right(l.charge_id, 3) as int)
where regexp_matches(l.charge_id, '^[0-9]{{10}}$')""")

con.execute("""create table pf as
select order_id, pallet_id,
  sum(w) w_sum, count(*) n_lot, sum(is_matched) n_matched,
  sum(w * storage_h) / nullif(sum(w),0) storage_wmean,
  max(storage_h) storage_max,
  sum(w * mix_s) / nullif(sum(w),0) mix_wmean,
  sum(w * cycle_s) / nullif(sum(w),0) cycle_wmean,
  sum(w * p_bw) / nullif(sum(w),0) bw_wmean,
  sum(w * dev_sum) / nullif(sum(w),0) dev_sum_wmean,
  sum(w * dev_sum / nullif(sum_target,0)) / nullif(sum(w),0) dev_pct_wmean,
  max(dev_max) dev_max_max,
  sum(w * n_materials) / nullif(sum(w),0) nmat_wmean,
  sum(w * mb_ratio) / nullif(sum(w),0) mb_ratio_wmean,
  sum(w * coalesce(max_temp,0)) / nullif(sum(w * case when max_temp is null then 0 else 1 end),0) temp_wmean,
  sum(w * rpm) / nullif(sum(w * case when rpm is null then 0 else 1 end),0) rpm_wmean,
  sum(w * max_torque) / nullif(sum(w * case when max_torque is null then 0 else 1 end),0) tq_wmean,
  sum(w * energy_kwh) / nullif(sum(w * case when energy_kwh is null then 0 else 1 end),0) en_wmean,
  sum(w * max_ram) / nullif(sum(w * case when max_ram is null then 0 else 1 end),0) ram_wmean,
  arg_max(p_shift, w) shift_dom, arg_max(p_eq, w) eq_dom
from lmap group by 1,2""")

con.execute(f"""create table wide as
select w.*, f.n_lot, f.n_matched,
  case when f.storage_wmean is not null then 1 else 0 end has_prod,
  f.storage_wmean, f.storage_max, f.mix_wmean, f.cycle_wmean, f.bw_wmean,
  f.dev_sum_wmean, f.dev_pct_wmean, f.dev_max_max, f.nmat_wmean, f.mb_ratio_wmean,
  f.temp_wmean, f.rpm_wmean, f.tq_wmean, f.en_wmean, f.ram_wmean, f.shift_dom, f.eq_dom
from read_csv_auto('{W}') w
left join pf f on w.order_id = f.order_id and w.pallet_id = f.pallet_id""")
OUT = config.OUT / "masterbatch_mooney_wide_pallet_prod.csv"
con.execute(f"copy wide to '{OUT}' (header, delimiter ',')")
n, hp = con.execute("select count(*), sum(has_prod) from wide").fetchone()
print(f"[prod] {n:,} 行，生产特征覆盖 {hp:,}（{hp/n:.2%}），用时 {time.time()-t0:.0f}s -> {OUT}")
