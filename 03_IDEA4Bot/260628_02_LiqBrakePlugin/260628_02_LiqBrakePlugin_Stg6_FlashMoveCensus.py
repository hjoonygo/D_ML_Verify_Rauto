# -*- coding: utf-8 -*-
# [260628_02_LiqBrakePlugin_Stg6_FlashMoveCensus.py]
# ★캡틴 지시 (2026-06-28): 36개월간 '순간 5%+ 급등락'이 몇 번 있었나? 각각 최악 슬리피지 예상?
# ★정의: 단일 1분봉 한방향 이동 = max((open-low)/open[급락], (high-open)/open[급등]).
#   순간 급변동 = 이 값 >= 임계(3/5/7/10%). 인접 60분내 봉은 1사건으로 클러스터.
#   최악 슬리피지(그 사건) = 사건내 최대 1분봉 폭 = 스톱이 시가 근처면 체결이 극단까지 밀리는 최대.
#   ★우리 1m모델 = 시가 체결 가정 → 갭(시가가 청산가 관통)이면 모델보다 더 나쁨. 청산문턱 > 최악폭이면 갭관통 없음(안전).
# ★데이터 = Merged_Data.csv 36개월. REVoi 노출 교차. 라벨 무관(이건 가격사건·슬립폭 분석, 수익률 아님).
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
from rauto_cex import MMR_T2, LIQ_SLIP

PJSON = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")


def _p(*a):
    print(*a, flush=True)


def cluster(times, gap_min=60):
    """정렬된 시각들을 gap_min 분 내 인접하면 1사건으로 묶어 [(start,end,idxs)] 반환."""
    if len(times) == 0:
        return []
    ev = []; s = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or (times[i] - times[i - 1]) > pd.Timedelta(minutes=gap_min):
            ev.append((s, i - 1)); s = i
    return ev


def main():
    _p("=" * 92)
    _p("[260628_02 Stg6] 36개월 순간 급등락(5%+) 전수 + 최악 슬리피지 예상")
    _p("=" * 92)
    d1m = load_1m()
    o = d1m["open"].values; h = d1m["high"].values; l = d1m["low"].values
    down = (o - l) / o            # 봉내 급락폭(시가→저가)
    up = (h - o) / o              # 봉내 급등폭(시가→고가)
    move = np.maximum(down, up)   # 한방향 최대 이동
    sidx = d1m.index

    _p(f"데이터: 1m {len(d1m):,}봉 · {sidx.min():%Y-%m-%d} ~ {sidx.max():%Y-%m-%d}")
    _p("\n[임계별 단일 1분봉 급변동 — 봉 개수 & 사건 수(60분 클러스터)]")
    _p(f"  {'임계':>6}{'급변동봉수':>10}{'사건수':>8}{'급락사건':>9}{'급등사건':>9}")
    THRS = [0.03, 0.05, 0.07, 0.10]
    ev5 = None
    for thr in THRS:
        mask = move >= thr
        idxs = np.where(mask)[0]
        times = sidx[idxs]
        evs = cluster(list(times))
        n_down = n_up = 0
        ev_list = []
        for (a, b) in evs:
            seg = idxs[a:b + 1]
            mx = seg[np.argmax(move[seg])]
            is_down = down[mx] >= up[mx]
            n_down += is_down; n_up += (not is_down)
            ev_list.append((sidx[mx], is_down, move[mx], mx))
        _p(f"  {thr*100:>4.0f}% {int(mask.sum()):>9}{len(evs):>8}{n_down:>9}{n_up:>9}")
        if abs(thr - 0.05) < 1e-9:
            ev5 = ev_list

    # ── 5% 사건 상세 + REVoi 노출 + 최악 슬립 ──
    p = json.load(open(PJSON, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    fund = load_funding()
    T = REVoiBot({**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T["et"] = pd.to_datetime(T["et"]); T["xt"] = pd.to_datetime(T["xt"])

    _p(f"\n[순간 5%+ 급변동 사건 전체 = {len(ev5)}건] (최악 1분봉폭 = 그 사건 최악 슬립 상한)")
    _p(f"  {'시각':>16}{'방향':>6}{'최악1분봉폭':>11}{'REVoi노출':>10}")
    ev5_sorted = sorted(ev5, key=lambda x: -x[2])
    for t, is_down, mv, mi in ev5_sorted:
        held = T[(T["et"] <= t) & (T["xt"] >= t)]
        pos = "-"
        if len(held):
            s = int(held.iloc[0]["side"]); pos = ("롱" if s == 1 else "숏")
        _p(f"  {t:%Y-%m-%d %H:%M}{'급락' if is_down else '급등':>6}{mv*100:>10.2f}%{pos:>10}")
    mvs = np.array([e[2] for e in ev5])
    _p(f"\n  최악 슬립 통계: 최대 {mvs.max()*100:.2f}% · 중앙 {np.median(mvs)*100:.2f}% · 평균 {mvs.mean()*100:.2f}%")

    # ── 레버별 '갭 관통' 위험 (최악 1분봉폭 vs 청산문턱) ──
    _p("\n[레버별 청산문턱 hsd vs 5%+ 사건 — 갭 관통(청산조차 못함) 위험]")
    _p(f"  {'레버':>5}{'청산문턱hsd':>11}{'hsd초과 사건수':>14}{'안전(문턱>최악폭)':>16}")
    for lev in [3, 5, 10, 12, 14, 15, 17, 20, 25]:
        hsd = 1.0 / lev - MMR_T2 - LIQ_SLIP
        over = int((mvs > hsd).sum())
        safe = "✅ 전사건 흡수" if over == 0 else f"❌ {over}건 갭관통"
        _p(f"  {lev:>5}x{hsd*100:>10.2f}%{over:>12}건  {safe:>16}")
    _p(f"\n  ▶ 최악 1분봉폭 = {mvs.max()*100:.2f}%. 청산문턱이 이보다 크면(저레버) 갭관통 0 = 청산이 시가에 깔끔히 체결.")
    _p(f"    36개월 최악폭 {mvs.max()*100:.2f}% 흡수하려면 hsd>{mvs.max()*100:.2f}% → lev ≤ {int(np.floor(1/(mvs.max()+MMR_T2+LIQ_SLIP)))}배.")
    _p("[정직] 이건 1분봉 단위 '한방향 폭'. 봉내 실제 체결경로(틱)는 더 나쁠 수 있음(안전장치7). 누적(수분)급락은 별도.")
    return True


if __name__ == "__main__":
    main()
