# -*- coding: utf-8 -*-
# [cpcv_reopt_exit.py] held-out 재최적 — REV단독 파라미터를 다시 뽑되 R+P(70%) 청산을 박아, 청산 OFF vs ON을 같은 잣대로 (캡틴 지시 2026-06-25).
#   ★진짜 OOS(§5.7): 폴드마다 '자기 학습구간 Calmar'로만 후보 재선택(커닝0)→보류 test 채점. + train≤2024 최적→25~26 held-out 분기롱숏.
#   exit_on = 레짐적응스텝(불리레짐 fib×1.4·고변동 불간섭) + 구조 부분익절70%. 둘 다 gen_trades opt-in(§15.1).
import os, sys, json, time, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side, monthly
from cpcv_reopt import cmdd, fold_eval, run_cpcv
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__)); T0 = time.time()
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
TIGHT, TPF = 1.4, 0.7   # R+P(70%)
_RG = None


def _p(*a):
    print(*a, flush=True)
    open(os.path.join(HERE, "cpcv_reopt_exit_run.log"), "a", encoding="utf-8").write(" ".join(str(x) for x in a)+"\n")
def hm(s): return f"{int(s//3600)}h{int((s%3600)//60):02d}m"
def el(): return time.time()-T0


def scale_for(d1m, rev_tf, tight):
    """불리레짐(저변동Q1·극단쏠림, 고변동 제외) fib_scale 배열(rev_tf 봉격자)."""
    global _RG
    if _RG is None:
        _RG = pd.read_parquet(REG); _RG["timestamp"] = pd.to_datetime(_RG["timestamp"], utc=True).dt.tz_localize(None); _RG = _RG.set_index("timestamp").sort_index()
    dfx = TS.resample_tf(d1m[["open","high","low","close"]], rev_tf); idx = dfx.index
    pos = np.clip(np.searchsorted(_RG.index.values, idx.values, "right")-1, 0, len(_RG)-1)
    atr = _RG["atr60"].values[pos]; ls = np.abs(_RG["ls_s"].values[pos])
    aq20, aq80 = np.nanquantile(atr,0.2), np.nanquantile(atr,0.8); lq80 = np.nanquantile(ls,0.8)
    adverse = (atr <= aq20) | ((ls >= lq80) & (atr < aq80))
    return np.where(adverse, tight, 1.0).astype(float)


def sample(rng):
    return dict(rev_tf=int(rng.choice([240,480,720])), piv=int(rng.choice([20,60,240])), N=int(rng.integers(2,9)),
                f1=float(rng.uniform(0.15,0.45)), f2=float(rng.uniform(0.45,0.65)), f3=float(rng.uniform(0.65,0.92)),
                iam=float(rng.uniform(0.5,3.0)), q=float(rng.uniform(0.2,0.4)), qwin=int(rng.integers(20,80)), arm=int(rng.integers(2,12)))


def rev_T(d1m, fund, p, exit_on):
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc = scale_for(d1m, p["rev_tf"], TIGHT) if exit_on else None
    return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"], er_gate=0.0,
                        ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"],
                        fib_scale=sc, tp_frac=(TPF if exit_on else 0.0))


def cand_monthly(d1m, fund, p, cal, exit_on):
    T = rev_T(d1m, fund, p, exit_on)
    m = monthly(T)
    if len(m) == 0: return None
    return pd.Series(m.values, index=pd.PeriodIndex(m.index, freq="M")).reindex(cal, fill_value=0.0).values


def build_set(d1m, fund, cal, NC, exit_on, tag):
    rng = np.random.default_rng(7); cands=[]; series=[]
    for i in range(NC):
        p = sample(rng)
        try: s = cand_monthly(d1m, fund, p, cal, exit_on)
        except Exception: s = None
        if s is not None: cands.append(p); series.append(s)
        if (i+1) % 20 == 0: _p(f"  [{tag}] 후보 {i+1}/{NC} · 경과 {hm(el())}")
    return cands, series


def main():
    NC = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    _p(f"\n===== held-out 재최적 (REV단독, 청산 OFF vs R+P{int(TPF*100)}%) 후보{NC} {time.strftime('%H:%M')} =====")
    d1m = load_1m(); fund = load_funding()
    cal = pd.period_range(d1m.index.min().to_period("M"), d1m.index.max().to_period("M"), freq="M")
    g_std6 = [np.array(x) for x in np.array_split(np.arange(len(cal)), 6)]
    g_year = [np.where(np.array([m.year for m in cal])==y)[0] for y in sorted(set(m.year for m in cal))]
    res = {}
    for exit_on, tag in [(False,"청산OFF 기준"), (True,f"청산ON R+P{int(TPF*100)}%")]:
        _p(f"\n----- {tag} -----")
        cands, series = build_set(d1m, fund, cal, NC, exit_on, tag)
        _p(f"  유효후보 {len(cands)} · {hm(el())}")
        r2 = run_cpcv(f"{tag} 표준6 choose-2 (본선)", g_std6, 2, cands, series, cal)
        r1 = run_cpcv(f"{tag} 연도 leave-one-out (참고)", g_year, 1, cands, series, cal)
        res[tag] = dict(std6=r2, year=r1, cands=cands, series=series)

    # ── train≤2024 최적 후보의 2025~26 held-out 분기 롱숏 (청산ON) ──
    on = res[f"청산ON R+P{int(TPF*100)}%"]
    tr = np.array([m.year <= 2024 for m in cal])
    best = max(range(len(on["series"])), key=lambda k: (lambda t,md,_: (t/abs(md) if md<0 else t))(*cmdd(on["series"][k][tr])))
    bp = on["cands"][best]
    _p(f"\n[train≤2024 최적 후보(청산ON)] rev_tf{bp['rev_tf']} piv{bp['piv']} N{bp['N']} 피보({bp['f1']:.2f},{bp['f2']:.2f},{bp['f3']:.2f}) iam{bp['iam']:.2f} q{bp['q']:.2f}/qwin{bp['qwin']} arm{bp['arm']}")
    T = rev_T(d1m, fund, bp, True); T["q"] = pd.to_datetime(T.et).dt.to_period("Q").astype(str); T["yr"] = pd.to_datetime(T.et).dt.year
    oos = T[T.yr >= 2025].copy()
    # held-out 분기 롱숏 (R합·승률·복리는 R기반)
    rows = []
    for q, g in oos.groupby("q"):
        L = g[g.side==1]; S = g[g.side==-1]
        rows.append(dict(분기=q, 롱_거래=len(L), 롱_승률=round(100*(L.R>0).mean(),0) if len(L) else 0, 롱_R합=round(L.R.sum()*100,1),
                         숏_거래=len(S), 숏_승률=round(100*(S.R>0).mean(),0) if len(S) else 0, 숏_R합=round(S.R.sum()*100,1),
                         총_R합=round(g.R.sum()*100,1)))
    qt = pd.DataFrame(rows)
    # OOS 전체(2025~26) 월복리 지표
    om = monthly(oos); otot, omdd, ocagr = cmdd(om.values)
    _p(f"\n[held-out 2025~26 (청산ON 최적)] 거래{len(oos)} · 월복리 누적{otot:+.0f}% · MDD{omdd:.0f}% · 연환산{ocagr:+.0f}% · 롱R합{qt.롱_R합.sum():+.0f}%/숏R합{qt.숏_R합.sum():+.0f}%")
    _p(qt.to_string(index=False))

    # ── 저장 ──
    import bt_report as BR
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    import re
    nn = (max([int(m.group(1)) for d in os.listdir(BR.BTO) if (m:=re.match(rf"{today}_(\d+)_",d))]+[0])+1)
    b = f"{today}_{nn:02d}_RevoiExitUp_HeldoutReopt"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)
    off = res["청산OFF 기준"]["std6"]; onr = on["std6"]
    cmp = pd.DataFrame([
        dict(구분="청산 OFF(기준)", CPCV_p25=round(off["p25"],1), CPCV_중앙=round(off["median"],1), 음수폴드pct=round(off["neg"],0), 폴드MDD최악=round(off["mdd_worst"],1), MDD20위반pct=round(off["mdd_viol"],0)),
        dict(구분=f"청산 ON R+P{int(TPF*100)}%", CPCV_p25=round(onr["p25"],1), CPCV_중앙=round(onr["median"],1), 음수폴드pct=round(onr["neg"],0), 폴드MDD최악=round(onr["mdd_worst"],1), MDD20위반pct=round(onr["mdd_viol"],0)),
    ])
    cmp.to_csv(os.path.join(folder, f"{b}_OOS비교표.csv"), index=False, encoding="utf-8-sig")
    qt.to_csv(os.path.join(folder, f"{b}_heldout분기롱숏.csv"), index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(2, 2, figsize=(16, 11))
    g = ["OFF 기준", f"ON R+P{int(TPF*100)}%"]
    ax[0,0].bar(g, [off["p25"], onr["p25"]], color=["#888","#26a69a"]); ax[0,0].axhline(0,color="black",lw=0.8)
    ax[0,0].set_title("held-out CPCV p25 연CAGR (재최적·OOS) (>0=진짜)", fontweight="bold"); ax[0,0].set_ylabel("p25 (%/yr)"); ax[0,0].grid(alpha=0.3,axis="y")
    for i,v in enumerate([off["p25"],onr["p25"]]): ax[0,0].text(i,v,f"{v:+.0f}",ha="center",va="bottom",fontsize=10)
    ax[0,1].bar(g, [off["mdd_viol"], onr["mdd_viol"]], color=["#888","#ef5350"])
    ax[0,1].set_title("held-out CPCV MDD-20 위반율 (0=본선통과)", fontweight="bold"); ax[0,1].set_ylabel("위반율 (%)"); ax[0,1].grid(alpha=0.3,axis="y")
    for i,v in enumerate([off["mdd_viol"],onr["mdd_viol"]]): ax[0,1].text(i,v,f"{v:.0f}",ha="center",va="bottom",fontsize=10)
    x = np.arange(len(qt)); ax[1,0].bar(x-0.2, qt.롱_R합, 0.4, color="#1e88e5", label="롱 Long R합"); ax[1,0].bar(x+0.2, qt.숏_R합, 0.4, color="#d81b60", label="숏 Short R합")
    ax[1,0].axhline(0,color="black",lw=0.8); ax[1,0].set_xticks(x); ax[1,0].set_xticklabels(qt.분기, rotation=45, fontsize=8)
    ax[1,0].set_title("held-out 2025~26 분기별 롱/숏 R합 (청산ON 최적·진짜OOS)", fontweight="bold"); ax[1,0].set_ylabel("R합 (%)"); ax[1,0].legend(); ax[1,0].grid(alpha=0.3,axis="y")
    c2 = ["#26a69a" if v>=0 else "#ef5350" for v in qt.총_R합]
    ax[1,1].bar(x, qt.총_R합, color=c2); ax[1,1].axhline(0,color="black",lw=0.8); ax[1,1].set_xticks(x); ax[1,1].set_xticklabels(qt.분기, rotation=45, fontsize=8)
    ax[1,1].set_title("held-out 2025~26 분기 총 R합 (%)", fontweight="bold"); ax[1,1].set_ylabel("총 R합 (%)"); ax[1,1].grid(alpha=0.3,axis="y")
    for i,v in enumerate(qt.총_R합): ax[1,1].text(i,v,f"{v:+.0f}",ha="center",va="bottom" if v>=0 else "top",fontsize=8)
    passed = onr["p25"]>0 and onr["mdd_viol"]==0
    fig.suptitle(f"REVoi held-out 재최적 — 청산 OFF vs R+P{int(TPF*100)}% (진짜 OOS·재선택·purge) — {b}\n"
                 f"본선판정: p25 {onr['p25']:+.0f}%/yr · MDD-20위반 {onr['mdd_viol']:.0f}% → {'통과(채택후보)' if passed else '미달'} | OFF p25 {off['p25']:+.0f}%/위반 {off['mdd_viol']:.0f}% · 영문/한글 병기",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.94]); png = os.path.join(folder, f"{b}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)

    body = (f"[held-out 재최적 — REV단독 청산 OFF vs R+P{int(TPF*100)}%] {b}\n"+"="*70+"\n"
        f"방법: 후보{NC}개 REV파라미터를 폴드마다 '자기 학습 Calmar'로만 재선택(커닝0)→보류 test OOS 채점(표준6=15경로). 청산만 OFF/ON 차이.\n\n"
        f"[본선 표준6 CPCV 비교]\n{cmp.to_string(index=False)}\n\n"
        f"[train≤2024 최적후보(청산ON)의 2025~26 held-out] 거래{len(oos)}·월복리{otot:+.0f}%·MDD{omdd:.0f}%·연환산{ocagr:+.0f}%·롱R합{qt.롱_R합.sum():+.0f}%/숏R합{qt.숏_R합.sum():+.0f}%\n{qt.to_string(index=False)}\n\n"
        f"판정: 청산ON p25 {onr['p25']:+.1f}% · MDD-20위반 {onr['mdd_viol']:.0f}% → {'★통과(p25>0·위반0)=§9 확정후보 승격 가능' if passed else '미달(헛수치 위 쌓기 금지)'}.\n"
        f"고딩 해설: 학습구간서만 고른 세팅을 한 번도 안 본 2025~26에 적용해도 분기마다 +이고 MDD-20 안 넘으면 '진짜'. OFF 대비 ON이 위반율↓·p25↑면 청산향상이 OOS에서도 유효.")
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: held-out재최적 청산ON p25{onr['p25']:+.0f}%/MDD20위반{onr['mdd_viol']:.0f}%(OFF p25{off['p25']:+.0f}%/위반{off['mdd_viol']:.0f}%)·{'통과' if passed else '미달'}|src=cpcv_reopt_exit.py\n")
    _p(f"\n[저장] {folder}\n  판정: 청산ON {'통과' if passed else '미달'} (p25 {onr['p25']:+.1f}%·MDD-20위반 {onr['mdd_viol']:.0f}%) | 총 {hm(el())}")


if __name__ == "__main__":
    main()
