# -*- coding: utf-8 -*-
# [REVoi_RegimeDiag] REVoi 휩소/레짐 필터 1단계=진단 (세션 260626_02_Rauto2_Sys).
#   캡틴 권장: REVoi+휩소/레짐필터(백테 진짜·하락장 PF0.05 약점). 전 기간(2023~2026-04)으로 '어느 레짐서 손실'인지 확정.
#   데이터 = Merged_Data(검증 oi_zscore, 2026 1~4월 포함). REVoi MDD25(lev3/sz75). per-trade honest.
#   측정(전부 진입시점 '과거만'=룩어헤드0): ①24h추세 ②72h추세 ③효율비ER(추세강도) ④변동성 → 버킷별 PF/평균R.
#   목적: PF 스프레드 큰 측정값 = 최적 게이트 후보 → 그걸로 손실레짐 진입차단 설계.
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths; ensure_paths()
import numpy as np, pandas as pd
from fib_replay_1m import load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel

MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")


def stats(R):
    R = np.array(R, float)
    if not len(R): return "거래0"
    w = R[R > 0]; l = R[R < 0]
    pf = (w.sum()/abs(l.sum())) if len(l) else 9.99
    return f"PF{pf:>4.2f} 승{round((R>0).mean()*100):>2}% 평균R{R.mean()*100:>+6.3f}% 복리{(np.prod(1+R)-1)*100:>+8.1f}% (n{len(R)})"


def main():
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]
    d = pd.read_csv(MERGED, usecols=["timestamp","open","high","low","close","oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open"]).set_index("t").sort_index()
    bot = REVoiBot(p)
    T = bot.make_trades(d, load_funding()).sort_values("et").reset_index(drop=True)
    pnl, fin, mdd, nl = per_trade_pnl(T, 75.0, 3.0, SlipModel(0,0))
    R = np.array(pnl)/100.0   # per-trade 사이즈드 수익률(분율)
    print("="*72); print("[REVoi 레짐 진단] 전 기간 2023-05~2026-04 · honest · 사이즈드"); print("="*72)
    print(f"전체: {stats(R)}  (앵커 +1851.6%)")

    cl = d["close"]; mc = cl.values; mt = d.index.values
    et = pd.to_datetime(T["et"]).values
    n = len(T); r24 = np.zeros(n); r72 = np.zeros(n); er = np.zeros(n); vol = np.zeros(n)
    for i in range(n):
        a = int(np.searchsorted(mt, np.datetime64(pd.Timestamp(et[i])), "left"))
        if a <= 0: continue
        a24 = max(0, a-1440); a72 = max(0, a-4320)
        r24[i] = (mc[a]/mc[a24]-1)*100
        r72[i] = (mc[a]/mc[a72]-1)*100
        seg = mc[a72:a+1]
        if len(seg) > 1:
            er[i] = abs(seg[-1]-seg[0])/(np.abs(np.diff(seg)).sum()+1e-9)   # 효율비(추세강도): 1=강추세,0=횡보
        h = d["high"].values[a24:a+1].max(); lo = d["low"].values[a24:a+1].min()
        vol[i] = (h-lo)/mc[a]*100

    def buckets(val, edges, names, title):
        print(f"\n[{title}]")
        lab = np.digitize(val, edges)
        for k, nm in enumerate(names):
            print(f"  {nm:<16} {stats(R[lab==k])}")

    # 24h 추세: 강하락 / 약하락 / 횡보 / 약상승 / 강상승
    buckets(r24, [-3,-1,1,3], ["강하락(<-3%)","약하락(-3~-1)","횡보(-1~1)","약상승(1~3)","강상승(>3%)"], "① 24h 추세별")
    # 72h(3일) 추세
    buckets(r72, [-6,-2,2,6], ["강하락(<-6%)","약하락(-6~-2)","횡보(-2~2)","약상승(2~6)","강상승(>6%)"], "② 72h(3일) 추세별")
    # 효율비 ER (추세강도): 낮음=횡보(역추세 유리), 높음=강추세(역추세 불리)
    buckets(er, [0.15,0.30,0.50], ["횡보ER<0.15","약ER0.15~0.30","중ER0.30~0.50","강추세ER>0.50"], "③ 효율비(추세강도)별 — 역추세는 횡보(낮은ER)서 유리 가설")
    # 변동성
    buckets(vol, [3,5,8], ["저변동<3%","중3~5%","고5~8%","초고>8%"], "④ 24h 변동성별")

    # 2026만(약한 해) 같은 분해 — 게이트가 2026 방어하나 확인용
    y = pd.to_datetime(T["et"]).dt.year.values
    R26 = R[y==2026]
    print(f"\n[2026만] 전체: {stats(R26)}")
    lab = np.digitize(r24, [-3,-1,1,3])
    print("  2026 24h추세별: ", end="")
    for k,nm in enumerate(["강하락","약하락","횡보","약상승","강상승"]):
        m=(y==2026)&(lab==k); print(f"{nm} {stats(R[m])[:8]}", end="  ")
    print("\n\n[해석] PF 스프레드 가장 큰 측정값 = 게이트 후보. '하락추세·강추세서 PF<<1'이면 그 진입을 막는 게 휩소필터.")
    return True


if __name__ == "__main__":
    main()
