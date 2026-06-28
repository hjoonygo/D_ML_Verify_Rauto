# -*- coding: utf-8 -*-
# [analyze_backtest.py] 종합 백테 분석 리포트 (재사용 엔진, CLAUDE.md §5 자동화).
#   입력 ledger T: ret·side·year·et(entry_t)·[tag]. ret는 사이징/비용 반영 최종수익률.
#   출력: 36개월 총·CAGR(년복리)·월복리 / 롱숏별·년도별·월별 PF·RR·MDD / 초기SL / 그래프 png(영문 라벨).
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _dd(r):
    eq = np.cumprod(1 + r); pk = np.maximum.accumulate(eq); return (eq - pk) / pk, eq
def pf(r):
    g = r[r > 0].sum(); b = -r[r < 0].sum(); return g / b if b > 1e-12 else np.inf
def rr(r):
    w = r[r > 0]; l = r[r < 0]; return (w.mean() / -l.mean()) if len(l) and len(w) else 0


def analyze(T, name, outpng, years=3.0, cap0=10000.0):
    r = T["ret"].values; dd, eq = _dd(r)
    tot = (eq[-1] - 1) * 100
    cagr = (eq[-1] ** (1 / years) - 1) * 100
    mcomp = (eq[-1] ** (1 / (years * 12)) - 1) * 100
    mdd = dd.min() * 100; avg_dd = dd[dd < 0].mean() * 100 if (dd < 0).any() else 0
    print(f"\n===== 종합분석: {name} ({len(T)}거래 / {years*12:.0f}개월) =====")
    print(f"[수익] 총 {tot:+.0f}% | 년복리(CAGR) {cagr:+.1f}% | 월복리 {mcomp:+.2f}% | $1만→${cap0*eq[-1]:,.0f}")
    print(f"[품질] PF {pf(r):.2f} | RR(손익비) {rr(r):.2f} | 승률 {100*(r>0).mean():.0f}% | MDD {mdd:.1f}% | 평균낙폭 {avg_dd:.1f}%")
    for s, g in T.groupby("side"):
        gr = g.ret.values
        print(f"[{'롱' if s==1 else '숏'}] {len(g)}건 합{gr.sum()*100:+.0f}% PF{pf(gr):.2f} RR{rr(gr):.2f} 승{100*(gr>0).mean():.0f}%")
    print("[년도별]")
    for y, g in T.groupby("year"):
        d2, _ = _dd(g.ret.values)
        print(f"  {int(y)}: {len(g)}건 합{((1+g.ret).prod()-1)*100:+.0f}% PF{pf(g.ret.values):.2f} MDD{d2.min()*100:.0f}%")
    if "et" in T:
        T = T.copy(); T["ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
        mo = T.groupby("ym").ret.apply(lambda x: ((1 + x).prod() - 1) * 100)
        print(f"[월별] {len(mo)}개월 | 양수월 {100*(mo>0).mean():.0f}% | 최고 {mo.max():+.0f}% 최악 {mo.min():+.0f}%")
    if "tag" in T:
        isl = T[T.tag == "initial_SL"]
        print(f"[초기SL] {len(isl)}건({100*len(isl)/len(T):.0f}%) 손익합 {isl.ret.sum()*100:+.0f}%p")
    # ── 그래프 (영문) ──
    fig, ax = plt.subplots(2, 3, figsize=(16, 9))
    ax[0,0].plot(eq, c="navy"); ax[0,0].set_title(f"Equity ({tot:+.0f}%, CAGR {cagr:+.0f}%/yr)"); ax[0,0].set_ylabel("capital x")
    ax[0,1].fill_between(range(len(dd)), dd * 100, 0, color="crimson", alpha=.5); ax[0,1].set_title(f"Drawdown (MDD {mdd:.0f}%, avg {avg_dd:.0f}%)")
    yr = T.groupby("year").ret.apply(lambda x: ((1 + x).prod() - 1) * 100)
    ax[0,2].bar([str(int(y)) for y in yr.index], yr.values, color=["seagreen" if v > 0 else "crimson" for v in yr.values]); ax[0,2].set_title("Yearly Return %")
    ls = T.groupby("side").ret.apply(lambda x: x.sum() * 100)
    ax[1,0].bar(["Short" if s == -1 else "Long" for s in ls.index], ls.values, color="steelblue"); ax[1,0].set_title("Long/Short Sum %")
    if "ym" in T:
        ax[1,1].bar(range(len(mo)), mo.values, color=["seagreen" if v > 0 else "crimson" for v in mo.values]); ax[1,1].set_title(f"Monthly Return % ({100*(mo>0).mean():.0f}% positive)")
    ax[1,2].hist(r * 100, bins=40, color="slateblue", alpha=.7); ax[1,2].axvline(0, c="k", lw=.7); ax[1,2].set_title(f"Trade Return Dist (RR {rr(r):.2f})")
    plt.suptitle(name); plt.tight_layout(); plt.savefig(outpng, dpi=110); plt.close()
    print(f"[그래프] {outpng}")
    return dict(tot=tot, cagr=cagr, mcomp=mcomp, mdd=mdd, pf=pf(r), rr=rr(r))
