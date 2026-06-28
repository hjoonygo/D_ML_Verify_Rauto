# -*- coding: utf-8 -*-
# [make_exit_bug_graph.py] 청산 마커 어긋남 버그 고딩설명 그래프(한국어). 2026-03-17 청산건 실제데이터.
#   문제: 신호 7h봉인데 청산마커를 7h봉 '시작시각(04:00)'에 찍음 → 실제 체결은 7h창 뒤쪽(10:06, 다른 4h봉) → 4h차트서 어긋남.
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines"); sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m
import trendstack_signal_engine as TS
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__))

SL = 73609.0; WRONG_T = pd.Timestamp("2026-03-17 04:00"); RIGHT_T = pd.Timestamp("2026-03-17 10:06")


def main():
    d1m = load_1m()
    df4 = TS.resample_tf(d1m[["open", "high", "low", "close"]], 240)
    s = df4["2026-03-16 00:00":"2026-03-18 12:00"]
    fig, ax = plt.subplots(figsize=(14, 7))
    x = mdates.date2num(s.index.to_pydatetime()); w = 0.12
    for xi, (_, c) in zip(x, s.iterrows()):
        up = c.close >= c.open; col = "#26a69a" if up else "#ef5350"
        ax.plot([xi, xi], [c.low, c.high], color=col, lw=1, zorder=2)
        ax.add_patch(plt.Rectangle((xi - w / 2, min(c.open, c.close)), w, abs(c.close - c.open) or 1, color=col, zorder=2))
    # 7h 신호봉 [04:00~11:00] 음영
    a, b = mdates.date2num(WRONG_T.to_pydatetime()), mdates.date2num(pd.Timestamp("2026-03-17 11:00").to_pydatetime())
    ax.axvspan(a, b, color="#3b82f6", alpha=0.08, zorder=1)
    ax.text((a + b) / 2, s.high.max(), "신호 7h봉 하나 = 04:00 ~ 11:00\n(청산 탐색이 이 7시간 전체)", color="#3b82f6",
            ha="center", va="top", fontsize=11, fontweight="bold")
    # 스톱선
    ax.axhline(SL, color="orange", ls="--", lw=1.3)
    ax.text(x[0], SL, f" 스톱선 {SL:.0f}", color="darkorange", va="bottom", fontsize=10)
    # 틀린 마커(04:00) — 캔들 아래 떠있음
    ax.scatter([a], [SL], marker="x", s=400, color="red", lw=3, zorder=6)
    ax.annotate("[X] 틀린 위치 (마커가 7h봉 시작 04:00에 찍힘)\n이 시각 4h봉은 [73,723~74,652]\n→ 73,609는 캔들 아래로 '떠버림'",
                (a, SL), xytext=(a - 0.55, SL - 1400), color="red", fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="red", lw=1.5))
    # 맞는 마커(10:06) — 캔들에 붙음
    r = mdates.date2num(RIGHT_T.to_pydatetime())
    ax.scatter([r], [SL], marker="o", s=260, facecolors="none", edgecolors="#1d9e75", lw=3, zorder=6)
    ax.annotate("[O] 진짜 체결 (10:06)\n이 시각 4h봉 [73,512~74,418]\n→ 73,609가 캔들 안에 정확히 닿음",
                (r, SL), xytext=(r + 0.05, SL - 1600), color="#1d9e75", fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#1d9e75", lw=1.5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %Hh")); ax.xaxis.set_major_locator(mdates.HourLocator(interval=8))
    plt.xticks(rotation=30, fontsize=9)
    ax.set_title("청산 마커가 캔들서 뜨는 이유 — 신호는 7h봉, 체결은 그 봉 안 '실제시각'에 일어난다", fontsize=14, fontweight="bold")
    ax.set_ylabel("가격($)"); ax.grid(alpha=0.2); ax.set_facecolor("#0b0e13"); fig.patch.set_facecolor("#0b0e13")
    ax.tick_params(colors="#e6edf3"); ax.yaxis.label.set_color("#e6edf3"); ax.title.set_color("#e6edf3")
    for sp in ax.spines.values(): sp.set_color("#27303a")
    plt.tight_layout(); out = os.path.join(HERE, "exit_bug_explain.png"); plt.savefig(out, dpi=120, facecolor="#0b0e13")
    print(f"[그래프] {out}")


if __name__ == "__main__":
    main()
