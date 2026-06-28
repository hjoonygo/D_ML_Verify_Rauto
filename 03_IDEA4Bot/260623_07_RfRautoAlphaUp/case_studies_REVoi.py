# -*- coding: utf-8 -*-
# [case_studies_REVoi.py] REVoi 거래 예시 6개 → 영문·한글 병기 그래프 + 고딩 해설 (캡틴 지시 2026-06-25).
#   ★캡틴 핵심: 예시는 'TV에서 볼 수 있는' 거래여야 한다 = Pine 임베드 범위(최근 400거래, index>=532)에서만 선택.
#     그래야 캡틴이 TradingView(BINANCE:BTCUSDT.P·UTC·4h)에서 직접 대조·인지 가능.
#   각 사례: 4h 캔들 배경 + 진입/청산/눌림목 마커 + 레짐주석 + 고딩 해설. 폰트=맑은고딕(한글 안깨짐).
import os, sys
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import matplotlib.dates as mdates
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as BR
import bt_full as B

# 한글폰트(맑은고딕) — 영문한글병기 라벨 안깨짐
FP = r"C:\Windows\Fonts\malgun.ttf"
fm.fontManager.addfont(FP); plt.rcParams["font.family"] = fm.FontProperties(fname=FP).get_name()
plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__))
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
OUTDIR = r"D:\ML\RfRauto\00_WorkHstr\BackTest_Output\260624_13_REVoi_MDD25_36mo_v6"
EMBED_FROM = 532   # 전체932 중 Pine 임베드(최근400) 시작 index = TV 가시범위. 그 이전은 예시 제외.


def _p(*a): print(*a, flush=True)


def draw_candles(ax, g):
    w = (g.index[1]-g.index[0]) * 0.6 if len(g) > 1 else pd.Timedelta(hours=2)
    for t, r in g.iterrows():
        up = r.close >= r.open; col = "#26a69a" if up else "#ef5350"
        ax.plot([t, t], [r.low, r.high], color=col, lw=0.8, zorder=1)
        ax.add_patch(plt.Rectangle((mdates.date2num(t)-mdates.date2num(t-w/2)+mdates.date2num(g.index[0])-mdates.date2num(g.index[0]), min(r.open,r.close)),
                                   0, 0))  # noop(자리)
        lo, hi = min(r.open, r.close), max(r.open, r.close)
        ax.bar(t, hi-lo, bottom=lo, width=w, color=col, edgecolor=col, zorder=2)


def main():
    p = json.load(open(os.path.join(HERE, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = BR.rev_trades(d1m, fund, p, capture_fills=True).sort_values("et").reset_index(drop=True)
    R = pd.read_parquet(REG); R["timestamp"] = pd.to_datetime(R["timestamp"], utc=True).dt.tz_localize(None)
    R = R.set_index("timestamp").sort_index()
    pos = np.clip(np.searchsorted(R.index.values, T.et.values, "right")-1, 0, len(R)-1)
    T["atr60"] = R["atr60"].values[pos]; T["oiz_abs"] = np.abs(R["oiz_s"].values[pos])
    T["atrQ"] = pd.qcut(T.atr60, 5, labels=[1,2,3,4,5]).astype(int)
    g4 = B.swings_on_tf  # not used directly
    lo_sw, hi_sw = B.swings_on_tf(d1m, p["piv"], p["N"])   # 눌림목(저/고)
    lo_df = pd.DataFrame(lo_sw, columns=["t","px"]); hi_df = pd.DataFrame(hi_sw, columns=["t","px"])
    df4 = B.TS.resample_tf(d1m[["open","high","low","close"]], p["rev_tf"])   # 4h 캔들

    # TV 가시범위(index>=532)만 후보
    V = T[T.index >= EMBED_FROM].copy()
    V["R%"] = V.R*100
    seen = set()
    def pick(name, mask, by, asc):
        s = V[mask & (~V.index.isin(seen))].sort_values(by, ascending=asc)
        if len(s): seen.add(s.index[0]); return (name, s.index[0])
        return None
    cands = [
        pick("①고변동 큰수익 High-vol BIG WIN", (V.R>0)&(V.atrQ>=4), "R%", False),
        pick("②롱 수익 LONG WIN", (V.R>0)&(V.side==1), "R%", False),
        pick("③MDD창 손실 Drawdown LOSS (2025-12~2026-01)", (V.R<0)&(V.et>="2025-12-01")&(V.et<="2026-02-01"), "R%", True),
        pick("④저변동 횡보 손실 Low-vol CHOP LOSS", (V.R<0)&(V.atrQ<=2), "R%", True),
        pick("⑤숏 수익 SHORT WIN", (V.R>0)&(V.side==-1), "R%", False),
        pick("⑥롱 손실 LONG LOSS", (V.R<0)&(V.side==1), "R%", True),
    ]
    final = [c for c in cands if c]
    # 빈 슬롯 보충(가장 극단 R부터 distinct)
    extra = list(V.sort_values("R%").index) + list(V.sort_values("R%", ascending=False).index)
    for ix in extra:
        if len(final) >= 6: break
        if ix not in seen: seen.add(ix); final.append((f"⑦보충 Extra", ix))
    final = final[:6]

    fig, axes = plt.subplots(3, 2, figsize=(17, 15)); axes = axes.flatten()
    expl = []
    for ax,(nm,ix) in zip(axes, final):
        r = T.loc[ix]; side = int(r.side); win = r.R>0
        pad_l = pd.Timedelta(minutes=p["rev_tf"]*8); pad_r = pd.Timedelta(minutes=p["rev_tf"]*5)
        t0, t1 = pd.Timestamp(r.et)-pad_l, pd.Timestamp(r.xt)+pad_r
        g = df4.loc[t0:t1]
        if len(g) < 3: continue
        draw_candles(ax, g)
        # 진입(신호가=base) 삼각형 + 평단선 + 청산 ✕
        base = r.fills[0][1] if isinstance(r.fills,list) and r.fills else r.entry
        mk = "^" if side==1 else "v"; ecol = "#1e88e5" if side==1 else "#d81b60"
        ax.scatter([r.et],[base], marker=mk, s=240, color=ecol, edgecolor="black", zorder=5, label="Entry 진입")
        ax.scatter([r.et],[r.entry], marker="o", s=60, color="white", edgecolor=ecol, zorder=5)
        ax.hlines(r.entry, r.et, r.xt, color=ecol, lw=1.4, linestyle="-", zorder=4, label="Avg entry 평단")
        xc = "#1565c0" if win else "#c62828"
        ax.scatter([r.xt_fill],[r.exit], marker="X", s=240, color=xc, edgecolor="black", zorder=6, label="Exit 청산(fibstop)")
        # 눌림목(피보 스텝업 참조 구조) — 창내 저/고
        wl = lo_df[(lo_df.t>=t0)&(lo_df.t<=t1)]; wh = hi_df[(hi_df.t>=t0)&(hi_df.t<=t1)]
        ax.scatter(wl.t, wl.px, marker=".", s=70, color="#00897b", zorder=3, label="Pivot low 눌림목 저")
        ax.scatter(wh.t, wh.px, marker=".", s=70, color="#fb8c00", zorder=3, label="Pivot high 눌림목 고")
        # 주석
        sd = "Long 롱" if side==1 else "Short 숏"; res = "WIN 수익" if win else "LOSS 손실"
        ax.set_title(f"{nm}\nTrade #{ix} (TV가시 visible) · {sd} · R={r.R*100:+.2f}% · {res}", fontsize=11, fontweight="bold")
        ax.text(0.015, 0.97, f"진입E {pd.Timestamp(r.et):%y-%m-%d %H:%M}\n청산X {pd.Timestamp(r.xt):%y-%m-%d %H:%M}\n변동성Vol Q{int(r.atrQ)}/5 · |OIz|{r.oiz_abs:.2f}",
                transform=ax.transAxes, fontsize=8.5, va="top", ha="left",
                bbox=dict(boxstyle="round", fc="#fffde7", ec="gray", alpha=0.9))
        ax.set_ylabel("Price 가격 (USDT)", fontsize=9); ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M")); ax.tick_params(labelsize=7.5)
        if ax is axes[0]: ax.legend(fontsize=7.5, loc="lower left", framealpha=0.85)
        # 고딩 해설(텍스트파일)
        dur = (pd.Timestamp(r.xt)-pd.Timestamp(r.et))
        why = ("역추세 진입이 맞아 가격이 우리편으로 갔고, 피보 스텝업이 이익을 따라 올리다 청산." if win
               else "역추세로 들어갔는데 가격이 반대로 더 가서 피보 스텝업 스톱(fibstop)에 손절. "
                    + ("저변동 횡보라 방향 안 나오고 비용·노이즈에 깎임." if r.atrQ<=2 else "고변동에서 추세가 더 세서 역추세가 깨짐."))
        expl.append(f"[{nm}] Trade #{ix}\n  {sd} | 진입 {pd.Timestamp(r.et):%Y-%m-%d %H:%M} @ ${r.entry:,.0f} → 청산 {pd.Timestamp(r.xt):%Y-%m-%d %H:%M} @ ${r.exit:,.0f} ({dur})\n"
                    f"  결과 R={r.R*100:+.2f}% ({res}) · 청산이유=피보 스텝업 스톱 · 레짐: 변동성 Q{int(r.atrQ)}/5, |OI z|={r.oiz_abs:.2f}\n"
                    f"  해설: {why}\n  TV확인: BINANCE:BTCUSDT.P, UTC, 4h에서 {pd.Timestamp(r.et):%Y-%m-%d} 부근 {sd} 마커 대조.\n")

    fig.suptitle("REVoi 거래 예시 6선 — Case Studies (TV 가시범위 last 400) · 영문/한글 병기\n"
                 "▲▼=Entry 진입 · 선=Avg entry 평단 · X=Exit 청산(fibstop 피보스텝업) · 점=Pivot 눌림목 · 캔들=4h",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.95])
    png = os.path.join(OUTDIR, "260624_13_REVoi_사례6선_CaseStudies.png")
    fig.savefig(png, dpi=130); plt.close(fig)
    txt = os.path.join(OUTDIR, "260624_13_REVoi_사례6선_해설.txt")
    open(txt,"w",encoding="utf-8").write("REVoi 거래 예시 6선 — 고딩 해설 (TV 가시범위 index>=532, 캡틴 TV대조용)\n"
        "="*70+"\n"+ "\n".join(expl) +
        "\n[공통 패턴] 수익=역추세가 먹혀 피보 스텝업이 이익 추격 / 손실=고변동 추세지속 or 저변동 횡보서 스톱.\n")
    _p(f"[저장] {png}\n[저장] {txt}")
    for nm,ix in final: _p(f"  채택 사례 {nm} → Trade#{ix}")


if __name__ == "__main__":
    main()
