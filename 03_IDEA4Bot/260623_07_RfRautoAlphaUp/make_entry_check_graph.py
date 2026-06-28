# -*- coding: utf-8 -*-
# [make_entry_check_graph.py] 2025-10-28 진입건을 내 데이터 4h봉에 그대로 그려 마커가 캔들에 박히는지 확인.
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines"); sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m
import trendstack_signal_engine as TS
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import matplotlib.dates as mdates
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__))

FILLS = [("2025-10-28 17:59", 115246.7), ("2025-10-28 18:01", 115133.7), ("2025-10-28 18:01", 115098.8)]
AVG = 115159.7; EXIT_T = "2025-10-29 14:03"; EXIT_P = 112700.0  # 대략(−2.1%)


def main():
    d1m = load_1m(); df4 = TS.resample_tf(d1m[["open", "high", "low", "close"]], 240)
    s = df4["2025-10-27 00:00":"2025-10-30 00:00"]
    fig, ax = plt.subplots(figsize=(13, 7)); x = mdates.date2num(s.index.to_pydatetime()); w = 0.06
    for xi, (_, c) in zip(x, s.iterrows()):
        up = c.close >= c.open; col = "#26a69a" if up else "#ef5350"
        ax.plot([xi, xi], [c.low, c.high], color=col, lw=1.2, zorder=2)
        ax.add_patch(plt.Rectangle((xi - w / 2, min(c.open, c.close)), w, abs(c.close - c.open) or 1, color=col, zorder=2))
    # 16:00봉 강조
    b = df4.loc["2025-10-28 16:00"]; bx = mdates.date2num(pd.Timestamp("2025-10-28 16:00").to_pydatetime())
    ax.annotate(f"16:00 4h봉\n고{b.high:.0f} 저{b.low:.0f}\n(위꼬리 고점 17:18)", (bx, b.high), xytext=(bx - 0.5, b.high + 700),
                color="#caa53a", fontsize=10, fontweight="bold", arrowprops=dict(arrowstyle="->", color="#caa53a"))
    # 진입 3체결 = 흰 X
    for t, p in FILLS:
        tx = mdates.date2num(pd.Timestamp(t).to_pydatetime())
        ax.scatter([tx], [p], marker="x", s=200, color="white", lw=2.5, zorder=7)
    tx0 = mdates.date2num(pd.Timestamp(FILLS[0][0]).to_pydatetime())
    ex = mdates.date2num(pd.Timestamp(EXIT_T).to_pydatetime())
    ax.plot([tx0, ex], [AVG, AVG], color="#3b82f6", lw=1.3, zorder=5)
    ax.annotate(f"진입 3체결(17:59·18:01) @115,098~115,246\n평단 {AVG:.0f} = 16:00봉 위꼬리 안(고115,554 아래)",
                (tx0, AVG), xytext=(tx0 - 0.9, AVG - 2200), color="white", fontsize=11, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="white"))
    ax.scatter([ex], [EXIT_P], marker="x", s=200, color="#ff3d8b", lw=2.5, zorder=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %Hh")); ax.xaxis.set_major_locator(mdates.HourLocator(interval=8))
    plt.xticks(rotation=30, fontsize=9)
    ax.set_title("2025-10-28 진입건 — 내 데이터 4h봉에 그대로(흰X=3체결). 위꼬리에 박히나?", fontsize=13, fontweight="bold")
    ax.set_ylabel("가격($)"); ax.grid(alpha=0.2); ax.set_facecolor("#0b0e13"); fig.patch.set_facecolor("#0b0e13")
    ax.tick_params(colors="#e6edf3"); ax.yaxis.label.set_color("#e6edf3"); ax.title.set_color("#e6edf3")
    for sp in ax.spines.values(): sp.set_color("#27303a")
    plt.tight_layout(); out = os.path.join(HERE, "entry_check.png"); plt.savefig(out, dpi=120, facecolor="#0b0e13")
    print(f"[그래프] {out}")


if __name__ == "__main__":
    main()
