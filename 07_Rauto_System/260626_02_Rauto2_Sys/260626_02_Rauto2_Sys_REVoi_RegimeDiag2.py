# -*- coding: utf-8 -*-
# [REVoi_RegimeDiag2] REVoi 레짐 진단 2차 — 장기추세 게이트 + 4H ER (세션 260626_02_Rauto2_Sys).
#   1차 발견: REVoi는 급락(24h/72h 하락)엔 강함(PF2~4.8). 약점=상승랠리 숏. 6월 손실='지속 하락추세'(장기) 가설.
#   2차: ①7d/14d/30d 장기추세 ②4H ER(추세강도) ③방향(롱/숏)×추세 교차 → 지속하락서 롱이 밟히나 확정.
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
from fib_replay_1m import load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel
MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def stat(R):
    R = np.array(R, float)
    if not len(R): return "       거래0"
    w = R[R > 0]; l = R[R < 0]
    pf = (w.sum()/abs(l.sum())) if len(l) else 9.99
    return f"PF{pf:>4.2f} 승{round((R>0).mean()*100):>2}% R{R.mean()*100:>+5.2f}% 복리{(np.prod(1+R)-1)*100:>+7.0f}%(n{len(R)})"


def main():
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    d = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open"]).set_index("t").sort_index()
    bot = REVoiBot(p)
    T = bot.make_trades(d, load_funding()).sort_values("et").reset_index(drop=True)
    pnl, fin, mdd, nl = per_trade_pnl(T, 75.0, 3.0, SlipModel(0,0))
    R = np.array(pnl)/100.0
    side = T["side"].astype(int).values
    print("="*74); print(f"[REVoi 레짐진단2] 전체 {stat(R)}"); print("="*74)

    # 4H 종가 + 4H ER(14봉)
    c4 = TS.resample_tf(d[["open","high","low","close"]], 240)["close"]
    er4 = c4.diff().abs().rolling(14).apply(lambda x: abs(x.sum()), raw=True)  # placeholder
    # 효율비 = |c[-1]-c[-14]| / sum(|diff|), 14 4H봉
    net = (c4 - c4.shift(14)).abs()
    den = c4.diff().abs().rolling(14).sum()
    ER4 = (net/(den+1e-9))
    mc = d["close"].values; mt = d.index.values
    et = pd.to_datetime(T["et"]).values
    n = len(T); r7=np.zeros(n); r14=np.zeros(n); r30=np.zeros(n); er=np.zeros(n)
    er4_idx = ER4.index.values; er4_val = ER4.values
    for i in range(n):
        a = int(np.searchsorted(mt, np.datetime64(pd.Timestamp(et[i])), "left"))
        if a<=0: continue
        r7[i]=(mc[a]/mc[max(0,a-10080)]-1)*100
        r14[i]=(mc[a]/mc[max(0,a-20160)]-1)*100
        r30[i]=(mc[a]/mc[max(0,a-43200)]-1)*100
        j = int(np.searchsorted(er4_idx, np.datetime64(pd.Timestamp(et[i])), "right"))-1
        er[i] = er4_val[j] if 0<=j<len(er4_val) and er4_val[j]==er4_val[j] else 0.0

    def buck(val, edges, names, title):
        print(f"\n[{title}]"); lab=np.digitize(val,edges)
        for k,nm in enumerate(names): print(f"  {nm:<18}{stat(R[lab==k])}")

    buck(r14, [-8,-3,3,8], ["강하락<-8%","약하락-8~-3","횡보-3~3","약상승3~8","강상승>8%"], "① 14일(2주) 추세별")
    buck(r30, [-12,-4,4,12], ["강하락<-12%","약하락-12~-4","횡보-4~4","약상승4~12","강상승>12%"], "② 30일(1달) 추세별")
    buck(er, [0.15,0.30,0.45], ["횡보ER<0.15","약0.15~0.30","중0.30~0.45","강추세>0.45"], "③ 4H ER(추세강도)별 — 역추세 가설: 횡보(낮은ER) 유리")

    # ④ 방향 × 30일추세 (지속하락서 롱이 밟히나?)
    print("\n[④ 방향 × 30일추세] — 역추세 롱(급락 받아치기)이 '지속하락'서 깨지나")
    lab30 = np.digitize(r30, [-12,-4,4,12]); names=["강하락","약하락","횡보","약상승","강상승"]
    for k,nm in enumerate(names):
        L=(lab30==k)&(side==1); S=(lab30==k)&(side==-1)
        print(f"  {nm:<8} 롱:{stat(R[L])[:24]}   숏:{stat(R[S])[:24]}")
    print("\n[해석] 게이트후보 = PF<<1 버킷. 특히 '지속하락(30일↓)+롱'이 깨지면 그걸 막는 게 6월방어 휩소필터.")
    return True


if __name__ == "__main__":
    main()
