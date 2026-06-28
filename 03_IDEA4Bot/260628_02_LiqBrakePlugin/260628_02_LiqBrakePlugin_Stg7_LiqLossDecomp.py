# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg7_LiqLossDecomp.py]
# ★캡틴 질문 (2026-06-28): lev15(청산0)=8151% → lev20(청산2)=6122% 하락이 '강제청산으로 증거금 날아간 것'인가?
#   → 노출3.0 고정 lev15 vs lev20 per-trade 비교. 청산된 2건을 찾아 lev15(생존) vs lev20(청산) 손익 직접 대조.
# ★검증엔진만: per_trade_pnl. 노출3.0=lev15/증거금20% = lev20/증거금15%. 현실10bp. post-2024.
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def find_root():
    d = HERE
    for _ in range(7):
        if os.path.isdir(os.path.join(d, "08_BTC_Data")) and os.path.isdir(os.path.join(d, "04_공용엔진코드")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return r"D:\ML\RfRauto"


ROOT = find_root()
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
from path_finder import ensure_paths
ensure_paths()
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from rauto_live import per_trade_pnl
from rauto_cex import SlipModel, MMR_T2, LIQ_SLIP

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")


def _p(*a):
    print(*a, flush=True)


def main():
    _p("=" * 92)
    _p("[260628_02 Stg7] lev15→lev20 수익하락 분해 — 강제청산이 증거금 날린 것? (노출3.0 고정)")
    _p("=" * 92)
    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["et"] = pd.to_datetime(T["et"])
    Tp = T[T["et"] >= "2024-01-01"].reset_index(drop=True)
    slip = SlipModel(0, 0, 10.0)

    # 노출3.0 = lev15/증거금20% = lev20/증거금15%
    pnl15, bal15, mdd15, nl15 = per_trade_pnl(Tp, 20.0, 15, slip)
    pnl20, bal20, mdd20, nl20 = per_trade_pnl(Tp, 15.0, 20, slip)
    _p(f"\n[재현 확인] 노출3.0 · post-2024 · 현실10bp")
    _p(f"  lev15(증거금20%): {(bal15/10000-1)*100:+,.0f}% / MDD{mdd15:.1f}% / 강제청산 {nl15}")
    _p(f"  lev20(증거금15%): {(bal20/10000-1)*100:+,.0f}% / MDD{mdd20:.1f}% / 강제청산 {nl20}")

    hsd15 = 1.0 / 15 - MMR_T2 - LIQ_SLIP
    hsd20 = 1.0 / 20 - MMR_T2 - LIQ_SLIP
    _p(f"  청산문턱: lev15 {hsd15*100:.2f}% · lev20 {hsd20*100:.2f}%")

    # 청산된 거래 = lev20에서 mae<=-hsd20 (lev15에선 mae>-hsd15라 생존)
    mae = Tp["mae"].values.astype(float)
    liq20 = np.where(mae <= -hsd20)[0]
    _p(f"\n[lev20에서 강제청산된 거래 = {len(liq20)}건] (이 거래들이 lev15에선 청산 안 됨)")
    _p(f"  {'거래#':>5}{'진입일':>12}{'방향':>5}{'역행mae':>9}{'실현R':>9} | {'lev15 계좌손익%':>15}{'lev20 계좌손익%':>15}{'차이%p':>9}")
    tot_diff = 0.0
    for i in liq20:
        r = Tp.iloc[i]
        d15 = pnl15[i]; d20 = pnl20[i]
        diff = d20 - d15
        tot_diff += diff
        _p(f"  {i:>5}{pd.Timestamp(r['et']):%Y-%m-%d}{'롱' if r['side']==1 else '숏':>5}{r['mae']*100:>8.2f}%{r['R']*100:>8.2f}% | "
           f"{d15:>+14.2f}%{d20:>+14.2f}%{diff:>+8.2f}%p")
    _p(f"\n  ▶ 그 {len(liq20)}건 합산 거래시점 손익차(lev20-lev15) = {tot_diff:+.2f}%p (음수=lev20이 그 거래서 더 잃음)")

    # 나머지 거래는 동일한지 확인
    same = sum(1 for i in range(len(pnl15)) if i not in liq20 and abs(pnl15[i] - pnl20[i]) < 1e-9)
    _p(f"  나머지 {len(pnl15)-len(liq20)}건 중 lev15=lev20 동일 = {same}건 (노출 같아 비청산 거래는 손익 동일 확인)")

    _p("\n[해석]")
    _p("  · 노출3.0 같으니 청산 안 되는 거래는 lev15·lev20 손익 100% 동일.")
    _p("  · 차이는 오직 lev20서 청산된 위 거래들 — 각각 mae가 lev20 문턱(4.45%)보다 깊어 강제청산.")
    _p("  · 강제청산 손익 = -노출×(문턱hsd+비용) ≈ 증거금 대부분 소멸. 그 거래가 lev15선 되돌아와(역추세) 덜 잃거나 벌었다면 격차 발생.")
    _p("  · ★이 거래시점 손익차가 복리로 누적 = 최종 수익 8151%→6122% 하락의 정체.")
    return True


if __name__ == "__main__":
    main()
