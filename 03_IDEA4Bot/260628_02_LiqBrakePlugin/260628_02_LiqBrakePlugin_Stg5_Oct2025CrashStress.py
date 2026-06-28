# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg5_Oct2025CrashStress.py]
# ★캡틴 지시 (2026-06-28): 2025-10 실제 플래시크래시(12만→10만, $2.9B 청산·청산조차 불가)에
#   REVoi가 '진입 상태'였다면 어떻게 됐나? 실데이터로 정확히 계산.
# ★검증엔진만: REVoi_bot 거래원장 + 그 거래의 mae(실보유 역행)로 lev별 청산/손익 직접 계산(격리마진식).
# ★데이터 = Merged_Data.csv(2025-10 포함). 진입 지정가 무슬립 · 청산 현실10bp. 라벨강제(ret_guard).
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
from rauto_cex import MMR_T1, MMR_T2, LIQ_SLIP, LIQ_COST

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")


def _p(*a):
    print(*a, flush=True)


def main():
    _p("=" * 96)
    _p("[260628_02 Stg5] 2025-10 실제 플래시크래시 — REVoi 진입상태였다면? (실데이터 스트레스)")
    _p("=" * 96)
    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()

    # ── 1. 2025-10 가격 실체 ──
    oct_ = d1m[(d1m.index >= "2025-10-01") & (d1m.index < "2025-11-01")]
    hi = oct_["high"].max(); lo = oct_["low"].min()
    hit = oct_["high"].idxmax(); lot = oct_["low"].idxmin()
    # 최대 단일 1분봉 낙폭(고→저), 최대 연속낙폭(직전고점→저점)
    oct_d = oct_.copy()
    oct_d["bar_drop"] = (oct_d["low"] - oct_d["open"]) / oct_d["open"] * 100
    wbar = oct_d["bar_drop"].idxmin(); wbar_v = oct_d["bar_drop"].min()
    # 직전 최고가 대비 저점 낙폭(러닝)
    oct_d["runmax"] = oct_d["high"].cummax()
    oct_d["dd"] = (oct_d["low"] - oct_d["runmax"]) / oct_d["runmax"] * 100
    wdd = oct_d["dd"].idxmin(); wdd_v = oct_d["dd"].min()
    _p(f"\n[2025-10 BTC 가격] 최고 ${hi:,.0f}({hit:%m-%d %H:%M}) · 최저 ${lo:,.0f}({lot:%m-%d %H:%M})")
    _p(f"  최대 단일 1분봉 낙폭(시가→저가) = {wbar_v:.2f}% @ {wbar:%m-%d %H:%M}")
    _p(f"  최대 누적 낙폭(직전고점→저점) = {wdd_v:.2f}% @ {wdd:%m-%d %H:%M}")
    # 급락 당일 1시간 윈도우
    day = oct_d[(oct_d.index >= "2025-10-10") & (oct_d.index < "2025-10-12")]
    if len(day):
        dhi = day["high"].max(); dlo = day["low"].min()
        _p(f"  10/10~11: 고 ${dhi:,.0f} → 저 ${dlo:,.0f} = {(dlo-dhi)/dhi*100:.1f}% 급락")

    # ── 2. COMBO 거래원장 + 급락 시점 보유 거래 ──
    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["et"] = pd.to_datetime(T["et"]); T["xt"] = pd.to_datetime(T["xt"])
    tcrash = pd.Timestamp(wdd)  # 최저점 시각
    # 그 시각 보유중(et<=tcrash<=xt)이던 거래 + 2025-10 진입 거래 전부
    held = T[(T["et"] <= tcrash) & (T["xt"] >= tcrash)]
    octT = T[(T["et"] >= "2025-10-01") & (T["et"] < "2025-11-01")]
    _p(f"\n[급락 최저점({tcrash:%Y-%m-%d %H:%M}) 보유중이던 REVoi 거래] {len(held)}건")
    for _, r in held.iterrows():
        _p(f"  진입{r['et']:%m-%d %H:%M}→청산{r['xt']:%m-%d %H:%M} · {'롱' if r['side']==1 else '숏'} · 진입${r['entry']:,.0f} "
           f"· mae(역행){r['mae']*100:+.2f}% · 실현R{r['R']*100:+.2f}% · {r['reason']}")
    _p(f"\n[2025-10 진입 REVoi 거래 전체] {len(octT)}건 · 롱 {(octT['side']==1).sum()} / 숏 {(octT['side']==-1).sum()}")
    _p(f"  2025-10 거래 mae 최악 = {octT['mae'].min()*100:.2f}% · 실현R 합 {octT['R'].sum()*100:+.1f}%(언사이즈드)")
    worst_oct = octT.loc[octT['mae'].idxmin()] if len(octT) else None

    # ── 3. 급락 보유거래(또는 2025-10 최악)에 레버별 손익(격리마진) ──
    target = None
    if len(held):
        target = held.loc[held['mae'].idxmin()]   # 보유중 가장 역행 큰 거래
        tag = "급락 보유중 최악역행 거래"
    elif worst_oct is not None:
        target = worst_oct; tag = "2025-10 최악역행 거래"
    if target is not None:
        mae = float(target['mae']); R = float(target['R']); fnd = float(target['fund'])
        _p("\n" + "=" * 96)
        _p(f"[{tag}] {'롱' if target['side']==1 else '숏'} · 진입${target['entry']:,.0f} · 역행 mae {mae*100:+.2f}% · 실현R {R*100:+.2f}%")
        _p("=" * 96)
        _p(f"  {'레버':>5}{'증거금%':>8}{'노출':>6}{'청산문턱hsd':>11}{'청산?':>7}{'이 거래 계좌손익%':>18}")
        for lev in [3, 5, 10, 15, 17, 20, 25]:
            size = 3.0 / lev * 100.0   # 노출3.0 고정 비교
            if size > 100: size = 100.0
            exp = size / 100.0 * lev
            mmr = MMR_T2
            hsd = 1.0 / lev - mmr - LIQ_SLIP
            if mae <= -hsd:
                p_acct = -exp * (hsd + LIQ_COST + abs(fnd)) * 100   # 강제청산 손실(계좌%)
                liq = "청산"
            else:
                p_acct = R * exp * 100
                liq = "-"
            _p(f"  {lev:>5}x{size:>7.1f}%{exp:>6.2f}{hsd*100:>10.2f}%{liq:>7}{p_acct:>+17.2f}%")

    # ── 4. ★가상 worst-case: 급락 직전 고점에서 롱 진입 상태였다면 (노출3.0 고정) ──
    if len(day):
        ent = float(day["high"].max()); low = float(day["low"].min())
        mae_c = (low - ent) / ent
        _p("\n" + "=" * 96)
        _p(f"[★가상 worst-case — 급락 직전 고점 ${ent:,.0f}서 '롱 진입' 상태였다면] 최저 ${low:,.0f} = 역행 {mae_c*100:.1f}%")
        _p("  ※ 실제 REVoi는 그때 flat이었음. 이건 '만약 롱이었다면'의 최악가정(노출3.0 고정).")
        _p("=" * 96)
        _p(f"  {'레버':>5}{'증거금%':>8}{'청산문턱hsd':>11}{'청산?':>7}{'이 거래 계좌손익%':>18}{'  설명':>4}")
        for lev in [3, 5, 6, 10, 15, 17, 20]:
            size = 3.0 / lev * 100.0
            if size > 100: size = 100.0
            exp = size / 100.0 * lev
            hsd = 1.0 / lev - MMR_T2 - LIQ_SLIP
            if mae_c <= -hsd:
                ploss = -exp * (hsd + LIQ_COST) * 100   # 청산: 손실=증거금(한방한도)
                liq = "청산"; desc = "증거금까지만 손실(cap)"
            else:
                ploss = mae_c * exp * 100               # 비청산: 역행 전체를 노출배 먹음
                liq = "생존"; desc = "청산안됨=역행 전체 손실"
            _p(f"  {lev:>5}x{size:>7.1f}%{hsd*100:>10.2f}%{liq:>7}{ploss:>+17.2f}%  {desc}")
        _p("  ▶ ★고레버일수록 손실 적음(증거금 작아 청산이 손실 cap) = 캡틴 '강제청산 브레이크' 직관이 이 극단서 정확.")
        _p("    ↔ 단 정상장(역행 -1~5%)선 고레버=청산빈발=수익잠식(Stg1~4). = 트레이드오프(둘 다 진실).")

    _p("\n[★캡틴 우려 핵심 — '청산조차 못 하는' 갭]")
    _p("  격리마진 모델상 최대손실 = 증거금(한방한도). BUT 실제 2025-10처럼 유동성 소멸+갭 관통이면:")
    _p("  ① 우리 1m모델은 '그 1분봉 시가 체결'을 가정 → 시가도 청산가보다 한참 아래면 모델보다 더 큰 손실.")
    _p("  ② 격리마진 명목 최대=증거금이나, 파산가 초과 갭은 거래소 보험기금/clawback 영역(증거금 이상 가능).")
    _p("  → 고레버일수록 청산문턱이 가까워 '갭 관통' 확률↑. = 캡틴 우려가 정확. 저레버=청산문턱 멀어 갭 관통 어려움.")
    return True


if __name__ == "__main__":
    main()
