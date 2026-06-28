# -*- coding: utf-8 -*-
# [make_cases.py] Back2TV 표준 산출: 거래 예시 '6선' 영문·한글 병기 그래프 + 고딩 해설 (캡틴 지시 2026-06-25).
#   ★규칙(BACKTEST_OUTPUT_SYSTEM §7 / CLAUDE §20): 예시는 반드시 'TV 가시범위'(=Pine 임베드 최근 MAXEMBED거래)에서만 선택.
#     그래야 캡틴이 TradingView(BINANCE:BTCUSDT.P·UTC·해당TF)에서 직접 대조·인지 가능. 500거래이전(임베드밖)은 예시 금지.
#   ★그래프 = 영문/한글 병기(맑은고딕 임베드로 안깨짐) + 고딩 해설. 최소 5개(기본 6선: 고변동승·롱승·MDD손·횡보손·숏승·롱손).
#   build_cases(T, p, d1m, folder, base, max_embed=400) — T는 capture_fills=True 결과. make_back2tv가 호출.
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import matplotlib.dates as mdates
import bt_full as B

_FP = r"C:\Windows\Fonts\malgun.ttf"
try:
    fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"


def _candles(ax, g):
    w = (g.index[1]-g.index[0])*0.6 if len(g) > 1 else pd.Timedelta(hours=2)
    for t, r in g.iterrows():
        up = r.close >= r.open; col = "#26a69a" if up else "#ef5350"
        ax.plot([t, t], [r.low, r.high], color=col, lw=0.8, zorder=1)
        lo, hi = min(r.open, r.close), max(r.open, r.close)
        ax.bar(t, hi-lo, bottom=lo, width=w, color=col, edgecolor=col, zorder=2)


def build_cases(T, p, d1m, folder, base, max_embed=400):
    """거래 T(capture_fills) → 사례 6선 PNG + 해설 txt 저장. TV가시범위(최근 max_embed)에서만 선택. 반환 (png, txt, 채택list)."""
    T = T.sort_values("et").reset_index(drop=True)
    embed_from = max(0, len(T) - max_embed)   # = Pine 임베드 시작 = TV 가시 시작
    rev_tf = p["rev_tf"]
    # 레짐(과거전용 atr60·|oiz|) asof 결합
    try:
        R = pd.read_parquet(REG); R["timestamp"] = pd.to_datetime(R["timestamp"], utc=True).dt.tz_localize(None)
        R = R.set_index("timestamp").sort_index()
        pos = np.clip(np.searchsorted(R.index.values, T.et.values, "right")-1, 0, len(R)-1)
        T["atr60"] = R["atr60"].values[pos]; T["oiz_abs"] = np.abs(R["oiz_s"].values[pos])
    except Exception:
        T["atr60"] = 0.0; T["oiz_abs"] = 0.0
    T["atrQ"] = (pd.qcut(T.atr60, 5, labels=[1,2,3,4,5]).astype(int) if T.atr60.nunique() > 5 else 3)
    lo_sw, hi_sw = B.swings_on_tf(d1m, p["piv"], p["N"])
    lo_df = pd.DataFrame(lo_sw, columns=["t","px"]); hi_df = pd.DataFrame(hi_sw, columns=["t","px"])
    df4 = B.TS.resample_tf(d1m[["open","high","low","close"]], rev_tf)

    V = T[T.index >= embed_from].copy(); V["R%"] = V.R*100
    seen = set()
    def pick(name, mask, by, asc):
        s = V[mask & (~V.index.isin(seen))].sort_values(by, ascending=asc)
        if len(s): seen.add(s.index[0]); return (name, s.index[0])
        return None
    cands = [
        pick("①고변동 큰수익 High-vol BIG WIN", (V.R>0)&(V.atrQ>=4), "R%", False),
        pick("②롱 수익 LONG WIN", (V.R>0)&(V.side==1), "R%", False),
        pick("③최대낙폭 손실 Drawdown LOSS", (V.R<0), "R%", True),
        pick("④저변동 횡보 손실 Low-vol CHOP LOSS", (V.R<0)&(V.atrQ<=2), "R%", True),
        pick("⑤숏 수익 SHORT WIN", (V.R>0)&(V.side==-1), "R%", False),
        pick("⑥롱 손실 LONG LOSS", (V.R<0)&(V.side==1), "R%", True),
    ]
    final = [c for c in cands if c]
    for ix in list(V.sort_values("R%").index) + list(V.sort_values("R%", ascending=False).index):
        if len(final) >= 6: break
        if ix not in seen: seen.add(ix); final.append(("⑦보충 Extra", ix))
    final = final[:6]
    if len(final) < 5:
        return None, None, []   # 거래 부족(가시범위<5) — 침묵금지: 호출측이 경고

    fig, axes = plt.subplots(3, 2, figsize=(17, 15)); axes = axes.flatten(); expl = []
    for ax,(nm,ix) in zip(axes, final):
        r = T.loc[ix]; side = int(r.side); win = r.R>0
        t0 = pd.Timestamp(r.et)-pd.Timedelta(minutes=rev_tf*8); t1 = pd.Timestamp(r.xt)+pd.Timedelta(minutes=rev_tf*5)
        g = df4.loc[t0:t1]
        if len(g) < 3: continue
        _candles(ax, g)
        fills = r.fills if isinstance(r.fills, list) else []
        base_px = fills[0][1] if fills else r.entry
        mk = "^" if side==1 else "v"; ecol = "#1e88e5" if side==1 else "#d81b60"
        ax.scatter([r.et],[base_px], marker=mk, s=240, color=ecol, edgecolor="black", zorder=5, label="Entry 진입")
        ax.scatter([r.et],[r.entry], marker="o", s=60, color="white", edgecolor=ecol, zorder=5)
        ax.hlines(r.entry, r.et, r.xt, color=ecol, lw=1.4, zorder=4, label="Avg entry 평단")
        xc = "#1565c0" if win else "#c62828"
        ax.scatter([getattr(r,"xt_fill",r.xt)],[r.exit], marker="X", s=240, color=xc, edgecolor="black", zorder=6, label="Exit 청산(fibstop)")
        wl = lo_df[(lo_df.t>=t0)&(lo_df.t<=t1)]; wh = hi_df[(hi_df.t>=t0)&(hi_df.t<=t1)]
        ax.scatter(wl.t, wl.px, marker=".", s=70, color="#00897b", zorder=3, label="Pivot low 눌림목 저")
        ax.scatter(wh.t, wh.px, marker=".", s=70, color="#fb8c00", zorder=3, label="Pivot high 눌림목 고")
        sd = "Long 롱" if side==1 else "Short 숏"; res = "WIN 수익" if win else "LOSS 손실"
        ax.set_title(f"{nm}\nTrade #{ix} (TV가시 visible) · {sd} · R={r.R*100:+.2f}% · {res}", fontsize=11, fontweight="bold")
        ax.text(0.015, 0.97, f"진입E {pd.Timestamp(r.et):%y-%m-%d %H:%M}\n청산X {pd.Timestamp(r.xt):%y-%m-%d %H:%M}\n변동성Vol Q{int(r.atrQ)}/5 · |OIz|{r.oiz_abs:.2f}",
                transform=ax.transAxes, fontsize=8.5, va="top", ha="left",
                bbox=dict(boxstyle="round", fc="#fffde7", ec="gray", alpha=0.9))
        ax.set_ylabel("Price 가격 (USDT)", fontsize=9); ax.grid(alpha=0.25)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M")); ax.tick_params(labelsize=7.5)
        if ax is axes[0]: ax.legend(fontsize=7.5, loc="lower left", framealpha=0.85)
        dur = pd.Timestamp(r.xt)-pd.Timestamp(r.et)
        why = ("역추세 진입이 맞아 가격이 우리편으로 갔고, 피보 스텝업이 이익을 따라 올리다 청산." if win
               else "역추세로 들어갔는데 가격이 반대로 더 가 피보 스텝업 스톱(fibstop)에 손절. "
                    + ("저변동 횡보라 방향 안 나고 비용·노이즈에 깎임." if r.atrQ<=2 else "고변동에서 추세가 더 세 역추세가 깨짐."))
        expl.append(f"[{nm}] Trade #{ix}\n  {sd} | 진입 {pd.Timestamp(r.et):%Y-%m-%d %H:%M} @ ${r.entry:,.0f} → 청산 {pd.Timestamp(r.xt):%Y-%m-%d %H:%M} @ ${r.exit:,.0f} ({dur})\n"
                    f"  결과 R={r.R*100:+.2f}% ({res}) · 청산이유=피보 스텝업 스톱 · 레짐: 변동성 Q{int(r.atrQ)}/5, |OI z|={r.oiz_abs:.2f}\n"
                    f"  해설: {why}\n  TV확인: BINANCE:BTCUSDT.P, UTC, {rev_tf//60 if rev_tf%60==0 else rev_tf}h에서 {pd.Timestamp(r.et):%Y-%m-%d} 부근 {sd} 마커 대조.\n")
    fig.suptitle(f"{base} 거래 예시 6선 — Case Studies (TV 가시범위 최근{max_embed}) · 영문/한글 병기\n"
                 "▲▼=Entry 진입 · 선=Avg entry 평단 · X=Exit 청산(fibstop 피보스텝업) · 점=Pivot 눌림목 · 캔들=신호TF",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.95])
    png = os.path.join(folder, f"{base}_사례6선_CaseStudies.png"); fig.savefig(png, dpi=130); plt.close(fig)
    txt = os.path.join(folder, f"{base}_사례6선_해설.txt")
    open(txt,"w",encoding="utf-8").write(f"{base} 거래 예시 6선 — 고딩 해설 (TV 가시범위 최근{max_embed}거래, 캡틴 TV대조용)\n"
        + "="*70 + "\n" + "\n".join(expl)
        + "\n[공통] 수익=역추세 적중 후 피보 스텝업이 이익추격 / 손실=고변동 추세지속 or 저변동 횡보서 스톱.\n")
    return png, txt, [(nm, int(ix)) for nm, ix in final]
