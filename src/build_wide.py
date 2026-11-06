# -*- coding: utf-8 -*-
"""第 1 步：从三张原始表构建托盘级门尼宽表。

输入（放 data/ 下）：
  BatchMaterials.csv   母胶投料明细
  BatchHeader.csv      母胶车次档案
  datamart*.csv        门尼检测

输出：output/masterbatch_mooney_wide_pallet.csv
口径说明见 README。
"""
import duckdb, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

config.check([config.BM, config.BH])
DM = config.datamart()
OUT = config.OUT / "masterbatch_mooney_wide_pallet.csv"

con = duckdb.connect()
con.execute("SET threads=4")

con.execute(f"create view bm as select * from read_csv('{config.BM}', all_varchar=true, nullstr='NULL')")
con.execute(f"create view bh as select * from read_csv_auto('{config.BH}', sample_size=-1)")
con.execute(f"create view dm as select * from read_csv('{DM}', all_varchar=true, nullstr='NULL')")

def log(s):
    print(s, flush=True)

log("[0] 门尼表里的托盘")
con.execute("""
create table dmp as
select distinct cast(order_id as int) oid, cast(pallet_id as varchar) pid,
       try_cast(right(pallet_id,3) as int) p3
from dm
where regexp_matches(order_id,'^[0-9]{7}$') and regexp_matches(pallet_id,'^[0-9]{10}$')
""")
log("    " + str(con.execute("select count(*) from dmp").fetchone()[0]))

log("[1] 托盘 -> 车次（BatchHeader）")
con.execute("""
create table pb as
select h.PalletID pid, cast(h.OrderID as varchar) oid, cast(h.BatchNumber as int) bn,
       h.BatchWeight bw, try_cast(h.MixingTimeSeconds as double) mix,
       h.BatchCycleTimeSeconds cyc, h.ShiftNumber shift, h.EquipmentID eq
from bh h join dmp d on h.PalletID = d.pid
""")
log("    车次 " + str(con.execute("select count(*) from pb").fetchone()[0])
    + "，托盘 " + str(con.execute("select count(distinct pid) from pb").fetchone()[0]))

log("[2] 母胶识别与车次级特征")
con.execute("""
create table bm_rows as
select OrderID oid, try_cast(BatchNumber as int) bn, try_cast(SequenceNumber as int) seq,
       MaterialCode mcode, MaterialName mname, ChargeID lot,
       try_cast(TargetWeight as double) tgt, try_cast(ActualWeight as double) act,
       try_cast(EffectiveConsumedWeight as double) eff,
       try_cast(ValidationIsExpired as int) expired,
       try_cast(Timestamp as timestamp) ts
from bm
where OrderID in (select distinct oid from pb) and try_cast(BatchNumber as int) is not null
""")
log("    投料行 " + str(con.execute("select count(*) from bm_rows").fetchone()[0]))

con.execute("""
create table ded as
select oid,bn,seq,mcode,lot,any_value(mname) mname,max(tgt) tgt,max(act) act,
       max(eff) eff,max(expired) expired,max(ts) ts
from bm_rows group by oid,bn,seq,mcode,lot
""")
con.execute("""
create table mat as
select oid,bn,mcode,any_value(mname) mname,count(distinct lot) n_lots,
       max(tgt) tgt_batch,max(act) act_batch,sum(eff) eff_sum,min(ts) use_ts,
       sum(expired) expired_cnt
from ded group by oid,bn,mcode
""")
con.execute("""
create table mst as
select * from (
  select *, row_number() over (partition by oid,bn
      order by coalesce(act_batch,eff_sum) desc nulls last) rn
  from mat
) where rn=1 and regexp_matches(mname,'^(M[0-9]|M3B|R1)-')
""")
log("    有母胶的车次 " + str(con.execute("select count(*) from mst").fetchone()[0]))

log("[3] 按托盘聚合")
con.execute("""
create table pf as
select p.pid, p.oid,
       count(*) n_batches,
       sum(bw) batch_weight_sum, avg(bw) batch_weight_mean,
       avg(mix) mix_time_mean, avg(cyc) cycle_time_mean,
       min(shift) shift, any_value(eq) eq,
       avg(m.act_batch) mb_act_mean, sum(m.act_batch) mb_act_sum,
       avg(m.tgt_batch) mb_tgt_mean,
       avg(m.act_batch - m.tgt_batch) dev_mean,
       max(abs(m.act_batch - m.tgt_batch)) dev_abs_max,
       avg(m.n_lots) n_lots_mean, count(distinct m.mcode) n_mb_materials,
       min(m.use_ts) use_ts
from pb p join mst m on p.oid=m.oid and p.bn=m.bn
group by 1,2
""")
log("    有母胶的托盘 " + str(con.execute("select count(*) from pf").fetchone()[0]))

log("[4] 门尼取数")
con.execute("""
create table dm_rows as
select cast(order_id as int) oid, cast(pallet_id as varchar) pid,
       compound_name, control_plan_category_name cat,
       try_cast(test_result as double) res, try_cast(test_target as double) mtgt,
       try_cast(retest_number as int) retest, test_status_name status,
       try_cast(test_result_start_time as timestamp) t
from dm
where regexp_matches(order_id,'^[0-9]{7}$') and regexp_matches(pallet_id,'^[0-9]{10}$')
  and substr(test_result_start_time,1,7) <> '2026-11'
  and (control_plan_category_name like 'L01%' or control_plan_category_name like 'L02%'
    or control_plan_category_name like 'L04%' or control_plan_category_name like 'R01%'
    or control_plan_category_name like 'R02%' or control_plan_category_name like 'C02%')
""")
con.execute("""
create table dm_agg as
with r as (select oid, pid, max(retest) mr from dm_rows group by 1,2)
select d.oid,d.pid, avg(d.res) mooney, any_value(d.mtgt) mooney_target,
       any_value(d.status) status, max(d.retest) retest, min(d.t) test_time,
       any_value(d.compound_name) compound, any_value(d.cat) cat, count(*) n_meas
from dm_rows d join r using(oid,pid) where d.retest=r.mr group by 1,2
""")

con.execute("""
create table wide as
with s as (select oid, min(p3) mn, max(p3) mx, count(*) sample_count from dmp group by 1)
select d.oid order_id, d.pid pallet_id, p.p3 pallet_no,
       case when p.p3=s.mn and p.p3=s.mx then 'only'
            when p.p3=s.mn then 'first' when p.p3=s.mx then 'last' else 'mid' end sample_pos,
       s.sample_count,
       d.compound, d.cat control_plan, d.mooney, d.mooney_target, d.status, d.retest,
       d.test_time, d.n_meas,
       f.n_batches, f.batch_weight_sum, f.batch_weight_mean, f.mix_time_mean,
       f.cycle_time_mean, f.shift, f.eq,
       f.mb_act_mean, f.mb_act_sum, f.mb_tgt_mean, f.dev_mean, f.dev_abs_max,
       f.n_lots_mean, f.n_mb_materials, f.use_ts
from dm_agg d
join dmp p on d.oid=p.oid and d.pid=p.pid
join s on s.oid = d.oid
join pf f on d.oid=f.oid and d.pid=f.pid
""")
con.execute(f"copy wide to '{OUT}' (header, delimiter ',')")
n = con.execute("select count(*) from wide").fetchone()[0]
o = con.execute("select count(distinct order_id) from wide").fetchone()[0]
c = con.execute("select count(distinct compound) from wide").fetchone()[0]
log(f"[5] 输出 {n:,} 行，{o:,} 订单，{c} 配方 -> {OUT}")
