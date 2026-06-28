# -*- coding: utf-8 -*-
# [exit_upgrade.py] 피보 스텝업 청산 향상 — 3레버를 순서대로 하나씩 A/B (캡틴 지시 2026-06-25, 세션 260625_01_RevoiExitRegime).
#   레버 T=시간손절(저변동 횡보출혈·비용) / R=레짐적응 스텝(MDD클러스터) / P=구조 부분익절(fat-tail 반납).
#   ★검증엔진만(§15.1): gen_trades에 opt-in 파라미터로만 확장(끄면 기존 동일). 사이징=격리마진 청산모델(MDD25 세팅 레버3/증거금75).
#   ★각 레버 = 상세 분석리포트(영문/한글 병기 그래프 + 고딩설명). 산출 = BackTest_Output\YYMMDD_NN_RevoiExitUp_(레버)\.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from fib_replay_1m import load_1m, load_funding
import bt_full as B
from blend_opt import rev_side
import bt_report as BR
_FP = r"C:\Windows\Fonts\malgun.ttf"
try: fm.fontManager.addfont(_FP); plt.rcParams["font.family"] = fm.FontProperties(fname=_FP).get_name()
except Exception: pass
plt.rcParams["axes.unicode_minus"] = False
HERE = os.path.dirname(os.path.abspath(__file__))
REG = r"D:\ML\RfRauto\08_BTC_Data\derived\_regime_features.parquet"
MMR_T1, MMR_T2, TIER, COST, SLIP = 0.004, 0.005, 50000.0, 0.0014, 0.0005
LEV, SZ = 3, 75   # MDD25 세팅(+1852% 앵커)와 동일 노출


def _p(*a): print(*a, flush=True)


def next_nn(today):
    """그날 BackTest_Output 폴더의 최대 NN+1(견고: 삭제·중복에도 유일 증가)."""
    import re
    ns = [int(m.group(1)) for d in os.listdir(BR.BTO) if (m := re.match(rf"{today}_(\d+)_", d))] if os.path.isdir(BR.BTO) else []
    return (max(ns)+1) if ns else 1


def gen(d1m, fund, p, ts_bars=0, ts_minR=0.0):
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                        er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False,
                        arm_bars=p["arm"], time_stop_bars=ts_bars, time_stop_minR=ts_minR)


def curve(T, size_pct=SZ, lev=LEV):
    """격리마진 청산복리 — 자본곡선 + 지표 반환(liq_eval 1:1 + 곡선)."""
    T = T.sort_values("et").reset_index(drop=True)
    R = T.R.values.astype(float); MAE = T.mae.values.astype(float); FUND = T.fund.values.astype(float)
    MK = pd.to_datetime(T.et).dt.to_period("M").astype(str).values
    exp = size_pct/100.0*lev; bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0; eq = []; mfac = {}
    for i in range(len(R)):
        mmr = MMR_T2 if exp*bal > TIER else MMR_T1; hsd = 1.0/lev - mmr - SLIP
        if MAE[i] <= -hsd: pnl = -exp*(hsd+COST+abs(FUND[i])); nliq += 1
        else: pnl = R[i]*exp
        bal *= (1.0+pnl); peak = max(peak, bal); mdd = min(mdd, bal/peak-1.0); eq.append(bal)
        mfac[MK[i]] = mfac.get(MK[i], 1.0)*(1.0+pnl)
    g = R[R > 0].sum(); b = -R[R < 0].sum()
    return dict(eq=np.array(eq), et=pd.to_datetime(T.et).values, tot=(bal/1e4-1)*100, mdd=mdd*100,
                nliq=nliq, win=100*(R > 0).mean(), pf=(g/b if b > 0 else np.inf), rsum=R.sum()*100,
                bestm=(max(mfac.values())-1)*100 if mfac else 0.0,
                nts=int((T.reason == "timestop").sum()), n=len(T),
                hold=((pd.to_datetime(T.xt)-pd.to_datetime(T.et)).dt.total_seconds()/60/T_TF).mean())


def lever_T(d1m, fund, p):
    global T_TF; T_TF = p["rev_tf"]
    _p("="*78); _p("[레버 T — 시간손절 A/B] 기준=MDD25 세팅(레버3·증거금75·+1852% 앵커)")
    base = curve(gen(d1m, fund, p))
    _p(f"  [기준 baseline] 거래{base['n']}·승{base['win']:.0f}%·PF{base['pf']:.2f}·복리{base['tot']:+.0f}%·MDD{base['mdd']:.0f}%·청산{base['nliq']}·평균보유{base['hold']:.1f}봉")
    rows = [("기준 OFF", 0, 0.0, base)]
    for N in [4, 6, 8, 10, 12, 16, 20]:
        c = curve(gen(d1m, fund, p, ts_bars=N, ts_minR=0.0))
        rows.append((f"N={N}", N, 0.0, c))
        _p(f"  N={N:<2} 시간손절: 거래{c['n']}·승{c['win']:.0f}%·PF{c['pf']:.2f}·복리{c['tot']:+.0f}%·MDD{c['mdd']:.0f}%·청산{c['nliq']}·시간손절{c['nts']}건·평균보유{c['hold']:.1f}봉")
    # 최고 복리 N에서 minR 변형
    best = max(rows[1:], key=lambda r: r[3]["tot"]); bestN = best[1]
    for thr in [-0.005, 0.003, 0.006]:
        c = curve(gen(d1m, fund, p, ts_bars=bestN, ts_minR=thr))
        rows.append((f"N={bestN},minR={thr:+.3f}", bestN, thr, c))
        _p(f"  N={bestN},minR{thr:+.3f}: 복리{c['tot']:+.0f}%·MDD{c['mdd']:.0f}%·시간손절{c['nts']}건")

    # ── 저장 폴더 ──
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True); nn = next_nn(today)
    b = f"{today}_{nn:02d}_RevoiExitUp_T_TimeStop"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)

    # ── 표 CSV ──
    tab = pd.DataFrame([dict(설정=nm, 시간손절봉=N, minR=thr, 거래수=c["n"], 승률=round(c["win"],1), PF=round(c["pf"],2),
                             복리수익=round(c["tot"],0), MDD=round(c["mdd"],1), 강제청산=c["nliq"], 시간손절건수=c["nts"],
                             평균보유봉=round(c["hold"],1), 단일최고월=round(c["bestm"],0)) for nm,N,thr,c in rows])
    tab.to_csv(os.path.join(folder, f"{b}_비교표.csv"), index=False, encoding="utf-8-sig")

    # ── 레짐(저변동 Q1) 분해: 시간손절이 횡보출혈을 잡나 ──
    Rg = pd.read_parquet(REG); Rg["timestamp"] = pd.to_datetime(Rg["timestamp"], utc=True).dt.tz_localize(None); Rg = Rg.set_index("timestamp").sort_index()
    def chop_rsum(T):
        pos = np.clip(np.searchsorted(Rg.index.values, pd.to_datetime(T.et).values, "right")-1, 0, len(Rg)-1)
        a = T.copy(); a["atr60"] = Rg["atr60"].values[pos]; q1 = a.atr60 <= a.atr60.quantile(0.2)
        return a[q1].R.sum()*100, int(q1.sum())
    base_chop = chop_rsum(gen(d1m, fund, p)); bestc = curve(gen(d1m, fund, p, ts_bars=bestN))
    var_chop = chop_rsum(gen(d1m, fund, p, ts_bars=bestN))

    # ── 그래프(영문/한글 병기·고딩) ──
    fig, ax = plt.subplots(2, 2, figsize=(16, 10))
    # (1) 자본곡선
    ax[0,0].plot(base["et"], base["eq"], color="#888", lw=1.6, label="기준 OFF Baseline")
    ax[0,0].plot(bestc["et"], bestc["eq"], color="#1e88e5", lw=1.8, label=f"시간손절 N={bestN} TimeStop")
    ax[0,0].set_yscale("log"); ax[0,0].set_title("자본곡선 Equity curve (로그 log $)", fontweight="bold")
    ax[0,0].set_ylabel("자본 Balance ($)"); ax[0,0].legend(fontsize=9); ax[0,0].grid(alpha=0.3)
    # (2) 복리수익 vs N
    Ns = [r[1] for r in rows if r[2]==0.0]; tots = [r[3]["tot"] for r in rows if r[2]==0.0]; mdds = [r[3]["mdd"] for r in rows if r[2]==0.0]
    xl = ["OFF" if n==0 else str(n) for n in Ns]
    ax[0,1].bar(xl, tots, color="#26a69a"); ax[0,1].set_title("복리수익 Return vs 시간손절봉 N", fontweight="bold")
    ax[0,1].set_ylabel("복리수익 Return (%)"); ax[0,1].grid(alpha=0.3, axis="y")
    for i,v in enumerate(tots): ax[0,1].text(i, v, f"{v:+.0f}", ha="center", va="bottom", fontsize=8)
    # (3) MDD vs N
    ax[1,0].bar(xl, mdds, color="#ef5350"); ax[1,0].axhline(-20, color="black", ls="--", lw=1, label="MDD -20% 본선 line")
    ax[1,0].set_title("최대낙폭 MDD vs 시간손절봉 N", fontweight="bold"); ax[1,0].set_ylabel("MDD (%)")
    ax[1,0].legend(fontsize=8); ax[1,0].grid(alpha=0.3, axis="y")
    for i,v in enumerate(mdds): ax[1,0].text(i, v, f"{v:.0f}", ha="center", va="top", fontsize=8)
    # (4) 저변동 횡보 R합 비교
    ax[1,1].bar(["기준 OFF\nBaseline", f"N={bestN}\nTimeStop"], [base_chop[0], var_chop[0]], color=["#888","#1e88e5"])
    ax[1,1].set_title(f"저변동 횡보(Q1, {base_chop[1]}거래) R합 — 시간손절 효과", fontweight="bold")
    ax[1,1].set_ylabel("R합 R-sum (%)"); ax[1,1].grid(alpha=0.3, axis="y")
    for i,v in enumerate([base_chop[0], var_chop[0]]): ax[1,1].text(i, v, f"{v:+.1f}", ha="center", va="bottom" if v>=0 else "top", fontsize=9)
    fig.suptitle(f"레버 T 시간손절 분석 Time-Stop Analysis — {b}\n"
                 f"기준 baseline 복리{base['tot']:+.0f}%/MDD{base['mdd']:.0f}% → 최적 N={bestN} 복리{bestc['tot']:+.0f}%/MDD{bestc['mdd']:.0f}% · 영문/한글 병기",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.94])
    png = os.path.join(folder, f"{b}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)

    # ── 분석 txt(고딩) ──
    body = (f"[레버 T 시간손절 분석] {b}\n"+"="*70+"\n"
        f"무엇: 진입 후 N봉이 지나도 평가손익이 +가 아니면(미진행) 종가에 시장청산. 저변동 횡보서 '비용·노이즈로 깎이는' 거래를 일찍 끊는다.\n"
        f"기준(시간손절 OFF): 복리 {base['tot']:+.0f}% · MDD {base['mdd']:.0f}% · 거래 {base['n']} · 승률 {base['win']:.0f}% · 평균보유 {base['hold']:.1f}봉\n"
        f"최적 N={bestN}:      복리 {bestc['tot']:+.0f}% · MDD {bestc['mdd']:.0f}% · 시간손절 {bestc['nts']}건 발동 · 평균보유 {bestc['hold']:.1f}봉\n"
        f"저변동 횡보(Q1) R합: 기준 {base_chop[0]:+.1f}% → N={bestN} {var_chop[0]:+.1f}%  (시간손절이 횡보출혈을 {'줄임' if var_chop[0]>base_chop[0] else '못줄임/악화'})\n\n"
        f"고딩 해설: 시간손절은 '오래 붙잡고 있어도 안 가는' 거래를 손절. 수익(복리)을 지키면서 MDD가 줄면 성공, 복리가 크게 깎이면 '좋은 거래까지 잘랐다'는 뜻.\n"
        f"판정 기준(§15·§20): full표본은 참고 — 채택은 CPCV 표준6 held-out·MDD−20 통과만. 다음=R(레짐적응 스텝).\n\n[비교표]\n"+tab.to_string(index=False))
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: 레버T 시간손절 A/B 최적N={bestN} 복리{bestc['tot']:+.0f}%/MDD{bestc['mdd']:.0f}%(기준{base['tot']:+.0f}%/{base['mdd']:.0f}%)|src=exit_upgrade.py\n")
    _p(f"\n[저장] {folder}\n  {b}_비교표.csv · {b}_분석그래프.png · {b}_분석.txt")
    return base, bestc, bestN


def build_scale(d1m, p, factor):
    """레짐적응 fib_scale 배열(sig_tf 봉별). 불리레짐(저변동 Q1·극단쏠림)서만 factor, ★고변동(Q5)은 절대 안건드림."""
    Rg = pd.read_parquet(REG); Rg["timestamp"] = pd.to_datetime(Rg["timestamp"], utc=True).dt.tz_localize(None); Rg = Rg.set_index("timestamp").sort_index()
    dfx = B.TS.resample_tf(d1m[["open","high","low","close"]], p["rev_tf"]); idx = dfx.index
    pos = np.clip(np.searchsorted(Rg.index.values, idx.values, "right")-1, 0, len(Rg)-1)
    atr = Rg["atr60"].values[pos]; ls = np.abs(Rg["ls_s"].values[pos])
    aq20, aq80 = np.nanquantile(atr, 0.2), np.nanquantile(atr, 0.8); lq80 = np.nanquantile(ls, 0.8)
    adverse = (atr <= aq20) | ((ls >= lq80) & (atr < aq80))   # ★고변동(atr>=aq80) 제외
    return np.where(adverse, factor, 1.0).astype(float), float(np.nanmean(adverse))


def lever_R(d1m, fund, p):
    global T_TF; T_TF = p["rev_tf"]
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    def gen_R(scale):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"], fib_scale=scale)
    _p("="*78); _p("[레버 R — 레짐적응 스텝 A/B] 불리레짐(저변동·극단쏠림)서만 타이트, 고변동 불간섭")
    base = curve(gen_R(None)); adv_frac = build_scale(d1m, p, 1.0)[1]
    _p(f"  [기준] 복리{base['tot']:+.0f}%·MDD{base['mdd']:.0f}%·승{base['win']:.0f}%·PF{base['pf']:.2f} (불리레짐 봉비중 {adv_frac*100:.0f}%)")
    rows = [("기준 OFF", 1.0, base)]
    for fct in [1.2, 1.4, 1.6, 2.0, 2.5]:
        sc, _ = build_scale(d1m, p, fct); c = curve(gen_R(sc)); rows.append((f"×{fct}", fct, c))
        _p(f"  타이트 ×{fct}: 복리{c['tot']:+.0f}%·MDD{c['mdd']:.0f}%·승{c['win']:.0f}%·PF{c['pf']:.2f}·청산{c['nliq']}")
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True); nn = next_nn(today)
    b = f"{today}_{nn:02d}_RevoiExitUp_R_RegimeStep"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)
    tab = pd.DataFrame([dict(설정=nm, 타이트배수=fct, 거래수=c["n"], 승률=round(c["win"],1), PF=round(c["pf"],2),
                             복리수익=round(c["tot"],0), MDD=round(c["mdd"],1), 강제청산=c["nliq"], 단일최고월=round(c["bestm"],0)) for nm,fct,c in rows])
    tab.to_csv(os.path.join(folder, f"{b}_비교표.csv"), index=False, encoding="utf-8-sig")
    bestrow = max(rows[1:], key=lambda r: (round(r[2]["mdd"],0), r[2]["tot"]))  # MDD 가장 얕은(동률=복리높은)
    bestc = bestrow[2]; bestf = bestrow[1]
    fig, ax = plt.subplots(2, 2, figsize=(16, 10))
    ax[0,0].plot(base["et"], base["eq"], color="#888", lw=1.6, label="기준 OFF Baseline")
    ax[0,0].plot(bestc["et"], bestc["eq"], color="#8e24aa", lw=1.8, label=f"레짐타이트 ×{bestf} Regime-tight")
    ax[0,0].set_yscale("log"); ax[0,0].set_title("자본곡선 Equity curve (로그 log $)", fontweight="bold")
    ax[0,0].set_ylabel("자본 Balance ($)"); ax[0,0].legend(fontsize=9); ax[0,0].grid(alpha=0.3)
    fs = [r[1] for r in rows]; tots = [r[2]["tot"] for r in rows]; mdds = [r[2]["mdd"] for r in rows]
    xl = ["OFF" if f==1.0 else f"x{f}" for f in fs]
    ax[0,1].bar(xl, tots, color="#26a69a"); ax[0,1].set_title("복리수익 Return vs 타이트배수", fontweight="bold")
    ax[0,1].set_ylabel("복리수익 Return (%)"); ax[0,1].grid(alpha=0.3, axis="y")
    for i,v in enumerate(tots): ax[0,1].text(i, v, f"{v:+.0f}", ha="center", va="bottom", fontsize=8)
    ax[1,0].bar(xl, mdds, color="#ef5350"); ax[1,0].axhline(-20, color="black", ls="--", lw=1, label="MDD -20% 본선")
    ax[1,0].set_title("최대낙폭 MDD vs 타이트배수", fontweight="bold"); ax[1,0].set_ylabel("MDD (%)"); ax[1,0].legend(fontsize=8); ax[1,0].grid(alpha=0.3, axis="y")
    for i,v in enumerate(mdds): ax[1,0].text(i, v, f"{v:.0f}", ha="center", va="top", fontsize=8)
    ax[1,1].scatter([r[2]["mdd"] for r in rows], [r[2]["tot"] for r in rows], s=90, color="#8e24aa")
    for nm,fct,c in rows: ax[1,1].annotate(("OFF" if fct==1.0 else f"x{fct}"), (c["mdd"], c["tot"]), fontsize=8, xytext=(4,4), textcoords="offset points")
    ax[1,1].axvline(-20, color="black", ls="--", lw=1); ax[1,1].set_title("MDD↔복리 트레이드오프 Trade-off", fontweight="bold")
    ax[1,1].set_xlabel("MDD (%)  ←왼쪽=나쁨"); ax[1,1].set_ylabel("복리수익 Return (%)"); ax[1,1].grid(alpha=0.3)
    fig.suptitle(f"레버 R 레짐적응 스텝 Regime-adaptive Step — {b}\n"
                 f"기준 복리{base['tot']:+.0f}%/MDD{base['mdd']:.0f}% → 타이트×{bestf} 복리{bestc['tot']:+.0f}%/MDD{bestc['mdd']:.0f}% (불리레짐봉 {adv_frac*100:.0f}%만 타이트·고변동 불간섭) · 영문/한글 병기",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93])
    png = os.path.join(folder, f"{b}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)
    body = (f"[레버 R 레짐적응 스텝 분석] {b}\n"+"="*70+"\n"
        f"무엇: 불리레짐(저변동 Q1·극단 롱숏쏠림, 봉비중 {adv_frac*100:.0f}%)에서만 피보 스텝 r을 ×배수로 키워 스톱을 가격쪽으로 더 빨리 당김(타이트). ★고변동(최고수익)은 안 건드림.\n"
        f"기준 OFF: 복리 {base['tot']:+.0f}% · MDD {base['mdd']:.1f}%\n"
        f"MDD최얕음 ×{bestf}: 복리 {bestc['tot']:+.0f}% · MDD {bestc['mdd']:.1f}% · 승률 {bestc['win']:.0f}% · PF {bestc['pf']:.2f}\n\n"
        f"고딩 해설: 불리한 장(횡보·쏠림극단)에서 손절을 더 바짝 따라붙여 '깨질 때 덜 잃게'. MDD가 -20 안으로 들어오면서 복리가 버티면 성공. 복리가 확 깎이면 너무 일찍 잘린 것.\n"
        f"판정(§15·§20): full표본 참고 — 채택은 CPCV 표준6 held-out·전폴드 MDD-20 통과만. 다음=P(구조 부분익절) 후 3레버 조합+CPCV.\n\n[비교표]\n"+tab.to_string(index=False))
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: 레버R 레짐적응스텝 MDD최얕음×{bestf} 복리{bestc['tot']:+.0f}%/MDD{bestc['mdd']:.0f}%(기준{base['tot']:+.0f}%/{base['mdd']:.0f}%)|src=exit_upgrade.py\n")
    _p(f"\n[저장] {folder}\n  {b}_비교표.csv · {b}_분석그래프.png · {b}_분석.txt")
    return base, bestc, bestf


def monthly_liq(T, size_pct=SZ, lev=LEV):
    """격리마진 청산 월별수익률 시리즈(CPCV용). 반환 (months PeriodIndex, ret array)."""
    T = T.sort_values("et").reset_index(drop=True)
    R = T.R.values.astype(float); MAE = T.mae.values.astype(float); FUND = T.fund.values.astype(float)
    MK = pd.to_datetime(T.et).dt.to_period("M"); exp = size_pct/100.0*lev
    pnl = np.empty(len(R))
    for i in range(len(R)):
        hsd = 1.0/lev - (MMR_T2 if exp*1e4 > TIER else MMR_T1) - SLIP   # 월수익률용 근사(잔고무관 보수)
        pnl[i] = -exp*(hsd+COST+abs(FUND[i])) if MAE[i] <= -hsd else R[i]*exp
    g = pd.DataFrame({"m": MK, "p": pnl}).groupby("m").p.apply(lambda x: (1+x).prod()-1)
    return g.index, g.values


def cpcv_std6(months, ret):
    """표준6그룹 choose-2=15경로 CPCV(월기준). 반환 dict(median,p25,worst,neg%,mdd_worst,mdd_viol%)."""
    import itertools
    if len(ret) < 12: return None
    g6 = np.array_split(np.arange(len(ret)), 6); cg = []; mdds = []
    for c in itertools.combinations(range(6), 2):
        te = np.sort(np.concatenate([g6[k] for k in c])); m = ret[te]
        eq = np.cumprod(1+m); tot = eq[-1]-1
        cagr = ((1+tot)**(12/len(m))-1)*100
        dd = ((eq-np.maximum.accumulate(eq))/np.maximum.accumulate(eq)).min()*100
        cg.append(cagr); mdds.append(dd)
    cg = np.array(cg); mdds = np.array(mdds)
    return dict(median=np.median(cg), p25=np.percentile(cg,25), worst=cg.min(), neg=100*(cg<0).mean(),
                mdd_worst=mdds.min(), mdd_viol=100*(mdds<-20).mean())


def _qret(T):
    """격리마진 분기수익률(복리) + 분기 롱/숏 R합 + 누적자본. 반환 DataFrame."""
    T = T.sort_values("et").reset_index(drop=True); T["q"] = pd.to_datetime(T.et).dt.to_period("Q").astype(str)
    exp = SZ/100.0*LEV; pnl = []
    for r in T.itertuples():
        hsd = 1.0/LEV - MMR_T1 - SLIP
        pnl.append(-exp*(hsd+COST+abs(r.fund)) if r.mae <= -hsd else r.R*exp)
    T["pnl"] = pnl; rows = []; cum = 10000.0
    for q, g in T.groupby("q"):
        L = g[g.side==1]; S = g[g.side==-1]; qf = (1+g.pnl).prod()-1; cum *= (1+qf)
        rows.append(dict(분기=q, 분기수익률=round(qf*100,1), 롱_R합=round(L.R.sum()*100,1), 숏_R합=round(S.R.sum()*100,1),
                         롱_거래=len(L), 숏_거래=len(S), 누적자본=round(cum,0)))
    return pd.DataFrame(rows)


def return_compare(d1m, fund, p, frac=0.7, tight=1.4):
    """★수익률 기준 보고: 36개월 전체 + 분기별, 롱/숏 구별. OFF vs ON(R+P). (CLAUDE §19 헤드라인 규칙)."""
    global T_TF; T_TF = p["rev_tf"]
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"]); sc, _ = build_scale(d1m, p, tight)
    def gen(scale, fr):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"],p["f2"],p["f3"]), p["iam"], er_gate=0.0,
                            ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"], fib_scale=scale, tp_frac=fr)
    Toff = gen(None, 0.0); Ton = gen(sc, frac); coff = curve(Toff); con = curve(Ton)
    qoff = _qret(Toff); qon = _qret(Ton)
    m = qoff[["분기","분기수익률"]].rename(columns={"분기수익률":"OFF_분기수익률"}).merge(
        qon.rename(columns={"분기수익률":"ON_분기수익률"}), on="분기")
    tab = m[["분기","OFF_분기수익률","ON_분기수익률","롱_R합","숏_R합","롱_거래","숏_거래","누적자본"]].rename(
        columns={"롱_R합":"ON_롱R합","숏_R합":"ON_숏R합","롱_거래":"ON_롱거래","숏_거래":"ON_숏거래","누적자본":"ON_누적자본"})
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    nn = next_nn(today); b = f"{today}_{nn:02d}_RevoiExitUp_ReturnCompare"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)
    tab.to_csv(os.path.join(folder, f"{b}_분기수익률표.csv"), index=False, encoding="utf-8-sig")
    _p("="*90); _p(f"[★수익률 기준 — 36개월 전체 + 분기별, 롱/숏] OFF vs ON R+P({int(frac*100)}%) (레버3·증거금75·$10k복리)")
    _p(f"  ◆ 36개월 전체 수익률: OFF {coff['tot']:+.0f}%  →  ON {con['tot']:+.0f}%  (누적 ${con['eq'][-1]:,.0f})")
    _p(f"  ◆ 롱/숏(ON): 롱 R합 {qon.롱_R합.sum():+.0f}% · 숏 R합 {qon.숏_R합.sum():+.0f}%")
    _p(tab.to_string(index=False))
    x = np.arange(len(tab)); fig, ax = plt.subplots(3, 1, figsize=(16, 14))
    ax[0].bar(x-0.2, tab.OFF_분기수익률, 0.4, color="#9e9e9e", label="OFF 기준 분기수익률"); ax[0].bar(x+0.2, tab.ON_분기수익률, 0.4, color="#26a69a", label=f"ON R+P{int(frac*100)}% 분기수익률")
    ax[0].axhline(0,color="black",lw=0.8); ax[0].set_title("분기별 수익률 Quarterly Return (%) — OFF vs ON (격리마진 복리)", fontweight="bold")
    ax[0].set_ylabel("분기수익률 Return (%)"); ax[0].set_xticks(x); ax[0].set_xticklabels(tab.분기, rotation=45, fontsize=8); ax[0].legend(); ax[0].grid(alpha=0.3,axis="y")
    for i in range(len(tab)): ax[0].text(x[i]+0.2, tab.ON_분기수익률[i], f"{tab.ON_분기수익률[i]:+.0f}", ha="center", va="bottom" if tab.ON_분기수익률[i]>=0 else "top", fontsize=6.5)
    ax[1].bar(x-0.2, tab.ON_롱R합, 0.4, color="#1e88e5", label="롱 Long R합"); ax[1].bar(x+0.2, tab.ON_숏R합, 0.4, color="#d81b60", label="숏 Short R합")
    ax[1].axhline(0,color="black",lw=0.8); ax[1].set_title(f"분기별 롱/숏 R합 (ON R+P{int(frac*100)}%) — 롱 {qon.롱_R합.sum():+.0f}% / 숏 {qon.숏_R합.sum():+.0f}%", fontweight="bold")
    ax[1].set_ylabel("R합 (%)"); ax[1].set_xticks(x); ax[1].set_xticklabels(tab.분기, rotation=45, fontsize=8); ax[1].legend(); ax[1].grid(alpha=0.3,axis="y")
    ax[2].plot(coff["et"], coff["eq"], color="#9e9e9e", lw=1.6, label=f"OFF 기준 ({coff['tot']:+.0f}%)"); ax[2].plot(con["et"], con["eq"], color="#26a69a", lw=2, label=f"ON R+P{int(frac*100)}% ({con['tot']:+.0f}%)")
    ax[2].set_yscale("log"); ax[2].set_title("36개월 자본곡선 Equity (로그 log, 시작 \\$10k)", fontweight="bold"); ax[2].set_ylabel("자본 Balance (\\$)"); ax[2].legend(fontsize=10); ax[2].grid(alpha=0.3)
    fig.suptitle(f"REVoi 청산향상 — 수익률 기준 보고 (36개월 전체 + 분기별 롱/숏) — {b}\n"
                 f"◆36개월 전체: OFF {coff['tot']:+.0f}% → ON R+P{int(frac*100)}% {con['tot']:+.0f}% (누적 \\${con['eq'][-1]:,.0f}) · 음수분기 {int((tab.ON_분기수익률<0).sum())}/{len(tab)} · 영문/한글 병기",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.95]); png = os.path.join(folder, f"{b}_분기수익률그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)
    body = (f"[★수익률 기준 보고 — 36개월 전체 + 분기별 롱/숏] {b}\n"+"="*70+"\n"
        f"◆ 36개월 전체 수익률: OFF {coff['tot']:+.0f}% → ON R+P({int(frac*100)}%) {con['tot']:+.0f}% (누적 ${con['eq'][-1]:,.0f}, 시작$10k)\n"
        f"◆ 롱/숏(ON): 롱 R합 {qon.롱_R합.sum():+.0f}% · 숏 R합 {qon.숏_R합.sum():+.0f}% (균형)\n"
        f"◆ 음수분기 {int((tab.ON_분기수익률<0).sum())}/{len(tab)}개\n\n[분기별 수익률 표]\n"+tab.to_string(index=False)+"\n\n"
        f"고딩 해설: 36개월 전체 수익률과 분기마다 얼마 벌었는지(+롱/숏)가 주인공. ON이 OFF보다 전체·분기 모두 높고 음수분기 적으면 청산향상이 수익률로 증명된 것.")
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: 수익률기준 36개월 OFF{coff['tot']:+.0f}%→ON{con['tot']:+.0f}%·분기롱숏(롱{qon.롱_R합.sum():+.0f}/숏{qon.숏_R합.sum():+.0f})|src=exit_upgrade.py\n")
    _p(f"\n[저장] {folder}\n  {b}_분기수익률표.csv · {b}_분기수익률그래프.png · {b}_분석.txt")
    return tab


def quarterly_report(d1m, fund, p, frac=0.7, tight=1.4):
    """최유력 R+P(70%)의 분기별(3개월) 롱/숏 분해 표 + 그래프 (캡틴 지시 2026-06-25 '알아볼 수 있게')."""
    global T_TF; T_TF = p["rev_tf"]
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc, _ = build_scale(d1m, p, tight)
    T = B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                     er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"],
                     fib_scale=sc, tp_frac=frac).sort_values("et").reset_index(drop=True)
    # 분기·롱숏 R합(레버리지無·가산), 총계는 격리마진 복리(분기수익률·누적$)
    T["q"] = pd.to_datetime(T.et).dt.to_period("Q").astype(str)
    exp = SZ/100.0*LEV; bal = 10000.0; pnl = []
    for r in T.itertuples():
        hsd = 1.0/LEV - MMR_T1 - SLIP
        pp = -exp*(hsd+COST+abs(r.fund)) if r.mae <= -hsd else r.R*exp
        pnl.append(pp)
    T["pnl"] = pnl
    rows = []; cum = 10000.0
    for q, g in T.groupby("q"):
        L = g[g.side == 1]; S = g[g.side == -1]
        qf = (1+g.pnl).prod()-1; cum *= (1+qf)
        rows.append(dict(분기=q,
            롱_거래=len(L), 롱_승률=round(100*(L.R>0).mean(),0) if len(L) else 0, 롱_R합=round(L.R.sum()*100,1),
            숏_거래=len(S), 숏_승률=round(100*(S.R>0).mean(),0) if len(S) else 0, 숏_R합=round(S.R.sum()*100,1),
            총_거래=len(g), 총_R합=round(g.R.sum()*100,1), 분기수익률=round(qf*100,1), 누적자본=round(cum,0)))
    tab = pd.DataFrame(rows)
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True); nn = next_nn(today)
    b = f"{today}_{nn:02d}_RevoiExitUp_Quarterly_LS"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)
    tab.to_csv(os.path.join(folder, f"{b}_분기롱숏표.csv"), index=False, encoding="utf-8-sig")
    _p("="*100); _p(f"[분기별 롱/숏 분해 — R+P({int(frac*100)}%) 최유력] (레버3·증거금75·시작$10k 복리)")
    _p(tab.to_string(index=False))

    qs = tab.분기.tolist(); x = np.arange(len(qs))
    fig, ax = plt.subplots(3, 1, figsize=(16, 14))
    # (1) 분기별 롱/숏 R합 그룹막대
    ax[0].bar(x-0.2, tab.롱_R합, 0.4, color="#1e88e5", label="롱 Long R합")
    ax[0].bar(x+0.2, tab.숏_R합, 0.4, color="#d81b60", label="숏 Short R합")
    ax[0].axhline(0, color="black", lw=0.8); ax[0].set_title("분기별 롱/숏 R합 Quarterly Long/Short R-sum (%) — 레버리지無·가산", fontweight="bold")
    ax[0].set_ylabel("R합 R-sum (%)"); ax[0].set_xticks(x); ax[0].set_xticklabels(qs, rotation=45, fontsize=8); ax[0].legend(); ax[0].grid(alpha=0.3, axis="y")
    for i in range(len(qs)):
        ax[0].text(x[i]-0.2, tab.롱_R합[i], f"{tab.롱_R합[i]:+.0f}", ha="center", va="bottom" if tab.롱_R합[i]>=0 else "top", fontsize=6.5)
        ax[0].text(x[i]+0.2, tab.숏_R합[i], f"{tab.숏_R합[i]:+.0f}", ha="center", va="bottom" if tab.숏_R합[i]>=0 else "top", fontsize=6.5)
    # (2) 분기수익률(복리) + 누적자본
    c2 = ["#26a69a" if v>=0 else "#ef5350" for v in tab.분기수익률]
    ax[1].bar(x, tab.분기수익률, color=c2); ax[1].axhline(0, color="black", lw=0.8)
    ax[1].set_title("분기 수익률 Quarterly Return (%, 격리마진 복리) — 막대 / 누적자본 Cum.\$ - 선", fontweight="bold")
    ax[1].set_ylabel("분기수익률 Return (%)"); ax[1].set_xticks(x); ax[1].set_xticklabels(qs, rotation=45, fontsize=8); ax[1].grid(alpha=0.3, axis="y")
    for i in range(len(qs)): ax[1].text(x[i], tab.분기수익률[i], f"{tab.분기수익률[i]:+.0f}", ha="center", va="bottom" if tab.분기수익률[i]>=0 else "top", fontsize=7)
    axt = ax[1].twinx(); axt.plot(x, tab.누적자본, color="#5c6bc0", lw=2, marker="o", ms=3, label="누적자본 Cumulative \$"); axt.set_yscale("log"); axt.set_ylabel("누적자본 Cum. \$ (log)")
    # (3) 분기별 롱/숏 승률
    ax[2].bar(x-0.2, tab.롱_승률, 0.4, color="#1e88e5", label="롱 Long 승률"); ax[2].bar(x+0.2, tab.숏_승률, 0.4, color="#d81b60", label="숏 Short 승률")
    ax[2].axhline(50, color="black", ls="--", lw=1, label="50%"); ax[2].set_title("분기별 롱/숏 승률 Quarterly Long/Short Win-rate (%)", fontweight="bold")
    ax[2].set_ylabel("승률 Win (%)"); ax[2].set_xticks(x); ax[2].set_xticklabels(qs, rotation=45, fontsize=8); ax[2].legend(); ax[2].grid(alpha=0.3, axis="y")
    fig.suptitle(f"REVoi 청산향상 R+P({int(frac*100)}%) — 분기별 롱/숏 분해 Quarterly Long/Short Breakdown — {b}\n"
                 f"36개월 누적 \${tab.누적자본.iloc[-1]:,.0f} (시작 \$10k) · 롱 R합 {tab.롱_R합.sum():+.0f}% / 숏 R합 {tab.숏_R합.sum():+.0f}% · 영문/한글 병기",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.95])
    png = os.path.join(folder, f"{b}_분기롱숏그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)
    body = (f"[분기별 롱/숏 분해 — R+P({int(frac*100)}%) 최유력] {b}\n"+"="*70+"\n"
        f"세팅: REVoi MDD25(레버3·증거금75) + 레짐적응스텝×{tight} + 구조 부분익절{int(frac*100)}%. 시작 $10k 복리.\n"
        f"36개월 누적자본 ${tab.누적자본.iloc[-1]:,.0f} · 롱 R합 {tab.롱_R합.sum():+.0f}% · 숏 R합 {tab.숏_R합.sum():+.0f}% (롱숏 균형 확인).\n"
        f"음수분기 {int((tab.분기수익률<0).sum())}/{len(tab)}개. 고딩 해설: 분기마다 롱·숏이 각각 얼마 벌었는지 = 한쪽 의존인지 균형인지 한눈에. 둘 다 +면 건강.\n\n"
        + tab.to_string(index=False))
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: R+P({int(frac*100)}%) 분기별 롱숏 분해 누적${tab.누적자본.iloc[-1]:,.0f}·롱{tab.롱_R합.sum():+.0f}%/숏{tab.숏_R합.sum():+.0f}%|src=exit_upgrade.py\n")
    _p(f"\n[저장] {folder}\n  {b}_분기롱숏표.csv · {b}_분기롱숏그래프.png · {b}_분석.txt")
    return tab


def lever_COMBO(d1m, fund, p):
    global T_TF; T_TF = p["rev_tf"]
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    sc14, _ = build_scale(d1m, p, 1.4)
    def gen(scale=None, frac=0.0):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"],
                            fib_scale=scale, tp_frac=frac)
    configs = [("기준 OFF", None, 0.0), ("R ×1.4", sc14, 0.0), ("P 익절50%", None, 0.5), ("P 익절70%", None, 0.7),
               ("R+P(50%)", sc14, 0.5), ("R+P(70%)", sc14, 0.7)]
    _p("="*78); _p("[3레버 조합 + CPCV 표준6 held-out 본선] (MDD25 세팅·레버3/증거금75)")
    rows = []
    for nm, sc, fr in configs:
        T = gen(sc, fr); c = curve(T); mo, rt = monthly_liq(T); cp = cpcv_std6(mo, rt)
        rows.append((nm, c, cp))
        _p(f"  [{nm:<10}] full: 복리{c['tot']:+.0f}%·MDD{c['mdd']:.0f}%·승{c['win']:.0f}% | CPCV p25 {cp['p25']:+.1f}%·중앙{cp['median']:+.1f}%·음수폴드{cp['neg']:.0f}%·폴드MDD최악{cp['mdd_worst']:.0f}%·MDD-20위반{cp['mdd_viol']:.0f}%")
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True); nn = next_nn(today)
    b = f"{today}_{nn:02d}_RevoiExitUp_COMBO_CPCV"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)
    tab = pd.DataFrame([dict(설정=nm, full복리=round(c["tot"],0), full_MDD=round(c["mdd"],1), 승률=round(c["win"],1),
                             CPCV_p25=round(cp["p25"],1), CPCV_중앙=round(cp["median"],1), 음수폴드pct=round(cp["neg"],0),
                             폴드MDD최악=round(cp["mdd_worst"],1), MDD20위반pct=round(cp["mdd_viol"],0)) for nm,c,cp in rows])
    tab.to_csv(os.path.join(folder, f"{b}_비교표.csv"), index=False, encoding="utf-8-sig")
    fig, ax = plt.subplots(2, 2, figsize=(16, 10)); nms = [r[0] for r in rows]
    p25s = [r[2]["p25"] for r in rows]; viol = [r[2]["mdd_viol"] for r in rows]; mw = [r[2]["mdd_worst"] for r in rows]; fmdd=[r[1]["mdd"] for r in rows]
    ax[0,0].bar(nms, p25s, color="#26a69a"); ax[0,0].axhline(0, color="black", lw=0.8); ax[0,0].set_title("CPCV p25 연CAGR (>0=수익엣지 진짜)", fontweight="bold")
    ax[0,0].set_ylabel("CPCV p25 (%/yr)"); ax[0,0].grid(alpha=0.3, axis="y"); ax[0,0].tick_params(axis="x", labelrotation=20, labelsize=8)
    for i,v in enumerate(p25s): ax[0,0].text(i, v, f"{v:+.0f}", ha="center", va="bottom", fontsize=8)
    ax[0,1].bar(nms, viol, color="#ef5350"); ax[0,1].axhline(0, color="black", lw=0.8); ax[0,1].set_title("CPCV 폴드 MDD-20 위반율 (0%=본선통과)", fontweight="bold")
    ax[0,1].set_ylabel("위반율 Violation (%)"); ax[0,1].grid(alpha=0.3, axis="y"); ax[0,1].tick_params(axis="x", labelrotation=20, labelsize=8)
    for i,v in enumerate(viol): ax[0,1].text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax[1,0].bar(nms, mw, color="#fb8c00"); ax[1,0].axhline(-20, color="black", ls="--", lw=1, label="MDD -20 본선"); ax[1,0].set_title("CPCV 폴드 최악 MDD Worst-fold MDD", fontweight="bold")
    ax[1,0].set_ylabel("최악 MDD (%)"); ax[1,0].legend(fontsize=8); ax[1,0].grid(alpha=0.3, axis="y"); ax[1,0].tick_params(axis="x", labelrotation=20, labelsize=8)
    for i,v in enumerate(mw): ax[1,0].text(i, v, f"{v:.0f}", ha="center", va="top", fontsize=8)
    ax[1,1].bar(nms, fmdd, color="#5c6bc0"); ax[1,1].axhline(-20, color="black", ls="--", lw=1); ax[1,1].set_title("full표본 MDD (참고)", fontweight="bold")
    ax[1,1].set_ylabel("full MDD (%)"); ax[1,1].grid(alpha=0.3, axis="y"); ax[1,1].tick_params(axis="x", labelrotation=20, labelsize=8)
    for i,v in enumerate(fmdd): ax[1,1].text(i, v, f"{v:.0f}", ha="center", va="top", fontsize=8)
    bestcp = max(rows, key=lambda r: (r[2]["mdd_viol"] <= 0, r[2]["p25"]))
    fig.suptitle(f"3레버 조합 + CPCV 표준6 본선 — {b}\n"
                 f"본선 통과(p25>0 & MDD-20위반0) 후보: {bestcp[0]} (p25 {bestcp[2]['p25']:+.0f}%·위반{bestcp[2]['mdd_viol']:.0f}%) · 영문/한글 병기",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93])
    png = os.path.join(folder, f"{b}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)
    body = (f"[3레버 조합 + CPCV 표준6 본선] {b}\n"+"="*70+"\n"
        f"★본선 기준(§5.7·§15): CPCV 표준6(15경로) p25>0 AND 전폴드 MDD-20위반 0%. full표본은 참고(과적합 상한).\n\n"+tab.to_string(index=False)+"\n\n"
        f"판정: 위반0 & p25>0 = '{bestcp[0]}'가 최유력. 통과 시 held-out 재확인 후 §9 확정후보 승격. 미통과면 추가 정밀화.\n"
        f"고딩 해설: full표본 좋아도 CPCV(여러 장세 잘라서 본 것)서 어느 구간이든 MDD-20 안넘고 수익(p25>0)이어야 '진짜'. 위반율이 0이어야 라이브 적합.")
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: 3레버조합 CPCV본선 최유력 {bestcp[0]}(p25{bestcp[2]['p25']:+.0f}%·MDD20위반{bestcp[2]['mdd_viol']:.0f}%)|src=exit_upgrade.py\n")
    _p(f"\n[저장] {folder}\n  최유력: {bestcp[0]} (CPCV p25 {bestcp[2]['p25']:+.1f}%·MDD-20위반 {bestcp[2]['mdd_viol']:.0f}%)")
    return rows


def lever_P(d1m, fund, p):
    global T_TF; T_TF = p["rev_tf"]
    _, side = rev_side(d1m, p["rev_tf"], p["q"], p["qwin"])
    def gen_P(frac):
        return B.gen_trades(d1m, fund, p["rev_tf"], p["piv"], p["N"], (p["f1"], p["f2"], p["f3"]), p["iam"],
                            er_gate=0.0, ext_side=side, align_pivot=True, use_trend_flip=False, arm_bars=p["arm"], tp_frac=frac)
    _p("="*78); _p("[레버 P — 구조 부분익절 A/B] 직전 반대편 눌림목 도달 시 일부 지정가 익절, 잔량 fibstop")
    base = curve(gen_P(0.0))
    Tb = gen_P(0.5); tp_rate = 100*Tb["tp"].mean() if "tp" in Tb.columns else 0.0
    _p(f"  [기준] 복리{base['tot']:+.0f}%·MDD{base['mdd']:.0f}%·승{base['win']:.0f}%·PF{base['pf']:.2f} | TP도달률 {tp_rate:.0f}%")
    rows = [("기준 OFF", 0.0, base)]
    for fr in [0.3, 0.5, 0.7, 1.0]:
        c = curve(gen_P(fr)); rows.append((f"익절{int(fr*100)}%", fr, c))
        _p(f"  부분익절 {int(fr*100)}%: 복리{c['tot']:+.0f}%·MDD{c['mdd']:.0f}%·승{c['win']:.0f}%·PF{c['pf']:.2f}")
    from datetime import datetime
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BR.BTO, exist_ok=True); nn = next_nn(today)
    b = f"{today}_{nn:02d}_RevoiExitUp_P_PartialTP"; folder = os.path.join(BR.BTO, b); os.makedirs(folder, exist_ok=True)
    tab = pd.DataFrame([dict(설정=nm, 익절비율=fr, 거래수=c["n"], 승률=round(c["win"],1), PF=round(c["pf"],2),
                             복리수익=round(c["tot"],0), MDD=round(c["mdd"],1), 강제청산=c["nliq"], 단일최고월=round(c["bestm"],0)) for nm,fr,c in rows])
    tab.to_csv(os.path.join(folder, f"{b}_비교표.csv"), index=False, encoding="utf-8-sig")
    bestrow = max(rows[1:], key=lambda r: (round(r[2]["mdd"],0), r[2]["tot"])); bestc = bestrow[2]; bestf = bestrow[1]
    fig, ax = plt.subplots(2, 2, figsize=(16, 10))
    ax[0,0].plot(base["et"], base["eq"], color="#888", lw=1.6, label="기준 OFF Baseline")
    ax[0,0].plot(bestc["et"], bestc["eq"], color="#00897b", lw=1.8, label=f"부분익절 {int(bestf*100)}% Partial-TP")
    ax[0,0].set_yscale("log"); ax[0,0].set_title("자본곡선 Equity curve (로그 log $)", fontweight="bold")
    ax[0,0].set_ylabel("자본 Balance ($)"); ax[0,0].legend(fontsize=9); ax[0,0].grid(alpha=0.3)
    frs = [r[1] for r in rows]; tots = [r[2]["tot"] for r in rows]; mdds = [r[2]["mdd"] for r in rows]; wins = [r[2]["win"] for r in rows]
    xl = ["OFF" if f==0.0 else f"{int(f*100)}%" for f in frs]
    ax[0,1].bar(xl, tots, color="#26a69a"); ax[0,1].set_title("복리수익 Return vs 익절비율", fontweight="bold")
    ax[0,1].set_ylabel("복리수익 Return (%)"); ax[0,1].grid(alpha=0.3, axis="y")
    for i,v in enumerate(tots): ax[0,1].text(i, v, f"{v:+.0f}", ha="center", va="bottom", fontsize=8)
    ax[1,0].bar(xl, mdds, color="#ef5350"); ax[1,0].axhline(-20, color="black", ls="--", lw=1, label="MDD -20% 본선")
    ax[1,0].set_title("최대낙폭 MDD vs 익절비율", fontweight="bold"); ax[1,0].set_ylabel("MDD (%)"); ax[1,0].legend(fontsize=8); ax[1,0].grid(alpha=0.3, axis="y")
    for i,v in enumerate(mdds): ax[1,0].text(i, v, f"{v:.0f}", ha="center", va="top", fontsize=8)
    ax[1,1].bar(xl, wins, color="#5c6bc0"); ax[1,1].set_title(f"승률 Win% vs 익절비율 (TP도달률 {tp_rate:.0f}%)", fontweight="bold")
    ax[1,1].set_ylabel("승률 Win (%)"); ax[1,1].grid(alpha=0.3, axis="y")
    for i,v in enumerate(wins): ax[1,1].text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    fig.suptitle(f"레버 P 구조 부분익절 Partial Take-Profit — {b}\n"
                 f"기준 복리{base['tot']:+.0f}%/MDD{base['mdd']:.0f}% → 익절{int(bestf*100)}% 복리{bestc['tot']:+.0f}%/MDD{bestc['mdd']:.0f}% · 영문/한글 병기",
                 fontsize=12, fontweight="bold")
    fig.tight_layout(rect=[0,0,1,0.93])
    png = os.path.join(folder, f"{b}_분석그래프.png"); fig.savefig(png, dpi=130); plt.close(fig)
    body = (f"[레버 P 구조 부분익절 분석] {b}\n"+"="*70+"\n"
        f"무엇: 역추세가 직전 반대편 눌림목(되돌림 목표)에 닿으면 그 비율만큼 지정가(maker) 익절, 잔량은 피보 스텝업 유지. TP도달률 {tp_rate:.0f}%.\n"
        f"기준 OFF: 복리 {base['tot']:+.0f}% · MDD {base['mdd']:.1f}% · 승률 {base['win']:.0f}%\n"
        f"MDD최얕음 익절{int(bestf*100)}%: 복리 {bestc['tot']:+.0f}% · MDD {bestc['mdd']:.1f}% · 승률 {bestc['win']:.0f}% · PF {bestc['pf']:.2f}\n\n"
        f"고딩 해설: 목표(직전 고/저)에 닿으면 일부 챙기고 나머지는 더 먹게 둠. 승률↑·수익반납↓이면 성공. 너무 많이 익절하면 큰 추세를 놓쳐 복리가 깎임.\n"
        f"판정(§15·§20): full표본 참고 — 채택은 CPCV 표준6 held-out·전폴드 MDD-20 통과만. 다음=3레버(R+P[+T]) 조합 → CPCV 본선.\n\n[비교표]\n"+tab.to_string(index=False))
    open(os.path.join(folder, f"{b}_분석.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(BR.WH, f"{ts}_{b}.txt"), "w", encoding="utf-8").write(body)
    with open(BR.INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|260625_01_RevoiExitRegime|{b}: 레버P 부분익절 MDD최얕음 익절{int(bestf*100)}% 복리{bestc['tot']:+.0f}%/MDD{bestc['mdd']:.0f}%(기준{base['tot']:+.0f}%/{base['mdd']:.0f}%)|src=exit_upgrade.py\n")
    _p(f"\n[저장] {folder}\n  {b}_비교표.csv · {b}_분석그래프.png · {b}_분석.txt")
    return base, bestc, bestf


def main():
    lever = sys.argv[1] if len(sys.argv) > 1 else "T"
    p = json.load(open(os.path.join(HERE, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    if lever == "T": lever_T(d1m, fund, p)
    elif lever == "R": lever_R(d1m, fund, p)
    elif lever == "P": lever_P(d1m, fund, p)
    elif lever == "COMBO": lever_COMBO(d1m, fund, p)
    elif lever == "Q": quarterly_report(d1m, fund, p)
    elif lever == "RET": return_compare(d1m, fund, p)
    else: _p(f"레버 {lever} 미구현. T·R·P·COMBO·Q·RET.")


if __name__ == "__main__":
    main()
