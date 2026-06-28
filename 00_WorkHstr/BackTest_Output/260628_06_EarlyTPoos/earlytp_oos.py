# -*- coding: utf-8 -*-
# [Stg6] early_tp 기여를 held-out OOS로, ★수익률(%)로 확인.
#   train(2024)에서 early_tp 최적 선택 → test(2025-01~2026-04, 블라인드) 수익률 ON vs OFF.
#   사이징 = OOS 배포기준 lev3/size75 고정(천장/레버최적 금지, CLAUDE.md §1). liq_eval 격리마진.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2
OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_06_EarlyTPoos"); os.makedirs(OUT, exist_ok=True)
PJSON = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
TRAIN_END = pd.Timestamp("2025-01-01")   # train=2024 / test=2025-01~2026-04 (둘 다 post-ETF)
SZ, LEV = 75.0, 3.0
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))
p_base = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
d1m = load_1m(); fund = load_funding()

def ret_split(p):
    T = B2.rev_trades(d1m, fund, p)
    et = pd.to_datetime(T["et"]).values
    R, M, F = T["R"].values, T["mae"].values, T["fund"].values
    K = pd.to_datetime(T["et"]).dt.strftime("%Y-%m").values
    tr = et < np.datetime64(TRAIN_END); te = ~tr
    def ev(m):
        if m.sum()==0: return (np.nan,np.nan,0)
        tot,mdd,bm,nl = B2.liq_eval(R[m],M[m],F[m],K[m],SZ,LEV)
        return (tot,mdd,int(m.sum()))
    return ev(tr), ev(te), len(T)

log("="*80); log("early_tp 기여 — held-out OOS 수익률(%)  [train=2024 / test=2025~2026, lev3/size75 고정]"); log("="*80)
log(f"{'config':28s} | {'train(2024) 수익%':>16s} {'tr_MDD':>7s} {'tr_n':>5s} | {'★test(2025~26) 수익%':>20s} {'te_MDD':>7s} {'te_n':>5s}")
log("-"*100)
rows=[]
# BASE(tp0,early0) 참고 + tp_frac0.7만(early off) = OFF 기준선 + early_tp 스윕
configs = [
    ("BASE tp0/early0", {**p_base}),
    ("tp0.7 / early OFF", {**p_base, "tp_frac":0.7}),
]
for e in [0.005, 0.0075, 0.01, 0.0125, 0.015]:
    configs.append((f"tp0.7 / early_tp {e*100:.2f}%", {**p_base, "tp_frac":0.7, "early_tp_pct":e, "early_frac":1.0}))
for name,p in configs:
    (trtot,trmdd,trn),(tetot,temdd,ten),ntot = ret_split(p)
    log(f"{name:28s} | {trtot:>+15,.0f}% {trmdd:>6.1f}% {trn:>5d} | {tetot:>+19,.0f}% {temdd:>6.1f}% {ten:>5d}")
    rows.append(dict(config=name, train_ret=round(trtot), train_mdd=round(trmdd,1),
                     test_ret=round(tetot), test_mdd=round(temdd,1), test_n=ten))
df=pd.DataFrame(rows); df.to_csv(os.path.join(OUT,"260628_06_EarlyTPoos_returns.csv"),index=False,encoding="utf-8-sig")

# 판정: train서 최적 early_tp 선택 → test 수익률 ON vs OFF
sweep = df[df.config.str.contains("early_tp")].copy()
off = df[df.config=="tp0.7 / early OFF"].iloc[0]
best_tr = sweep.loc[sweep.train_ret.idxmax()]
log("\n" + "="*80)
log("[★OOS 판정 — 전부 수익률 기준]")
log(f"  OFF(early 없음)           test 수익 = {off.test_ret:+,.0f}% (MDD{off.test_mdd}%)")
log(f"  train최적 early_tp = {best_tr.config.split('early_tp ')[1]} → test 수익 = {best_tr.test_ret:+,.0f}% (MDD{best_tr.test_mdd}%)")
diff = best_tr.test_ret - off.test_ret
mult = (best_tr.test_ret/off.test_ret) if off.test_ret not in (0,) and off.test_ret>0 else float('nan')
log(f"  → ★early_tp 기여(held-out test) = {diff:+,.0f}%p" + (f" ({mult:.1f}배)" if not np.isnan(mult) else ""))
# test서 가장 좋은 early_tp가 train최적과 같은가(과적합 점검)
best_te = sweep.loc[sweep.test_ret.idxmax()]
log(f"  과적합 점검: train최적={best_tr.config.split('early_tp ')[1]} · test최적={best_te.config.split('early_tp ')[1]} → {'일치(강건)' if best_tr.config==best_te.config else '불일치'}")
open(os.path.join(OUT,"260628_06_EarlyTPoos_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("\n[OK] -> "+OUT)
