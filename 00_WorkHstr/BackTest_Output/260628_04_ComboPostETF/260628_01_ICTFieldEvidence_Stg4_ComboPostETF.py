# -*- coding: utf-8 -*-
# [Stg4] COMBO 진짜 엔진을 full / 2023(pre-ETF) / 2024이후(post-ETF)로 잘라 정확한 수익률 산출.
#   앵커검증(+1851.6%) → COMBO full M0~M20(헤드라인 재현) → ★COMBO post-2024 M0~M20(캡틴 질문 정답).
#   검증엔진 무수정 호출(back2tv_REVoi.rev_trades / liq_eval). 격리마진·강제청산 실모델.
import os, sys, json
import numpy as np, pandas as pd
ROOT = r"D:\ML\RfRauto"
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths; ensure_paths()
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as B2

OUT = os.path.join(ROOT, r"00_WorkHstr\BackTest_Output\260628_04_ComboPostETF")
os.makedirs(OUT, exist_ok=True)
PJSON = os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json")
START = np.datetime64("2024-01-01")
lines=[]
def log(s=""): print(s, flush=True); lines.append(str(s))

p_base = json.load(open(PJSON))["REV_MDD25_36mo"]["p"]
combo_p = {**p_base, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}

log("="*82); log("COMBO 진짜 엔진 — full vs 2023(pre-ETF) vs 2024이후(post-ETF)  [260628_01 Stg4]"); log("="*82)
d1m = load_1m(); fund = load_funding()
log("[생성] COMBO 거래 생성중(1m체결·격리마진)…")
T  = B2.rev_trades(d1m, fund, combo_p)
Tb = B2.rev_trades(d1m, fund, p_base)   # 무손상 앵커용 BASE

et = pd.to_datetime(T["et"]).values
R, MAE, FUND = T["R"].values, T["mae"].values, T["fund"].values
MKEY = pd.to_datetime(T["et"]).dt.strftime("%Y-%m").values
mask_post = et >= START; mask_pre = ~mask_post

# 앵커검증(§15.2): BASE lev3/sz75 = +1851.6%?
anchor = 100.0*(np.prod(1 + Tb["R"].values*0.75*3.0)-1.0)
log(f"\n[앵커검증] BASE(tp0/early0) lev3/sz75 full = {anchor:+.1f}%  (기대 +1851.6% → {'일치' if abs(anchor-1851.6)<5 else '불일치!'})")
log(f"[COMBO 거래수] 전체={len(T)}  2023={int(mask_pre.sum())}  2024이후={int(mask_post.sum())}")
log(f"[무사이징 sumR] 전체={R.sum():+.3f}  2023={R[mask_pre].sum():+.3f}  2024이후={R[mask_post].sum():+.3f}")

def sweep(Rs, Ms, Fs, Ks):
    best={"M0":(-1e18,),"M30":(-1e18,),"M25":(-1e18,),"M20":(-1e18,)}
    for lev in range(2,21):
        tot,mdd,bm,nl = B2.liq_eval(Rs,Ms,Fs,Ks,75.0,float(lev))
        if tot>best["M0"][0]: best["M0"]=(tot,lev,mdd,nl)
        for tag,lim in [("M30",-30),("M25",-25),("M20",-20)]:
            if mdd>=lim and tot>best[tag][0]: best[tag]=(tot,lev,mdd,nl)
    return best

def fmt(t):
    if t[0]<=-1e17: return "  (없음)"
    tot,lev,mdd,nl=t
    rs=f"{tot:+,.0f}" if abs(tot)<1e6 else f"{tot:+.2e}"
    return f"{rs}% @lev{lev}/sz75 · MDD{mdd:.1f}% · 청산{nl}"

rows=[]
for name,m in [("전체 36개월", slice(None)), ("2023만 (pre-ETF)", mask_pre), ("★2024이후 (post-ETF)", mask_post)]:
    Rs,Ms,Fs,Ks = R[m],MAE[m],FUND[m],MKEY[m]
    b = sweep(Rs,Ms,Fs,Ks)
    log(f"\n[{name}]  거래 {len(Rs)}  (size75 lev스윕, 격리마진 정확)")
    for tag in ["M0","M30","M25","M20"]:
        log(f"   {tag:4s}: {fmt(b[tag])}")
    # 고정 lev3/sz75 (앵커와 동일 사이징) 단순비교
    t3 = B2.liq_eval(Rs,Ms,Fs,Ks,75.0,3.0)
    t5 = B2.liq_eval(Rs,Ms,Fs,Ks,75.0,5.0)
    log(f"   고정 lev3/sz75 = {t3[0]:+,.0f}% (MDD{t3[1]:.1f}%) · lev5/sz75 = {t5[0]:+,.0f}% (MDD{t5[1]:.1f}%)")
    rows.append({"기간":name,"거래":len(Rs),"무사이징sumR":round(Rs.sum(),3),
                 "M0":round(b['M0'][0]) if b['M0'][0]>-1e17 else None,
                 "M20":round(b['M20'][0]) if b['M20'][0]>-1e17 else None,
                 "M20_lev":b['M20'][1] if b['M20'][0]>-1e17 else None,
                 "M20_mdd":round(b['M20'][2],1) if b['M20'][0]>-1e17 else None,
                 "lev3_sz75":round(t3[0]),"lev3_mdd":round(t3[1],1)})
pd.DataFrame(rows).to_csv(os.path.join(OUT,"260628_04_ComboPostETF_summary.csv"),index=False,encoding="utf-8-sig")
open(os.path.join(OUT,"260628_04_ComboPostETF_analysis.txt"),"w",encoding="utf-8").write("\n".join(lines))
log("\n[OK] -> "+OUT)
