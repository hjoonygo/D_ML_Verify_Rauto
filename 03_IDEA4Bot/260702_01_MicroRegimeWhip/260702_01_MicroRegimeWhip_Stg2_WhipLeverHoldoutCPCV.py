# -*- coding: utf-8 -*-
# [260702_01_MicroRegimeWhip_Stg2_WhipLeverHoldoutCPCV] ★휩소 3지렛대 정직검증 — held-out + CPCV 표준6 (세션 260702_01_MicroRegimeWhip).
#   캡틴 지시(2026-07-01·Stg1 진단 후): Stg1이 지목한 저EV 병목(랠리·휩소하락)을 줄이는 3지렛대를
#     OOS(held-out·CPCV 표준6)로 나란히 비교 → '어느 게 실제로 바닥(floor)을 올리나' 판정. ★과적합 경계(WHIP_soft 전례).
#   3지렛대(전부 COMBO 챔피언 위 opt-in):
#     L1 하락ER게이트   = 하락(7일추세≤-3)&저ER(톱니휩소) → 사이징 ×0.5   [사이징 오버레이·§25 결정두뇌]
#     L2 랠리역주행억제  = 상승(7일추세≥+3)&역행(숏) → 사이징 ×0.5          [사이징 오버레이·§25]
#     L3 저EV통합       = (L1 ∪ L2) → 사이징 ×0.5                          [사이징 오버레이·§25]
#     EX 조기익절강화   = COMBO early_tp 1.0%→0.5%(전량) 원장 재생성         [봇 알파(청산)·전체원장]
#   ★검증엔진만(§8·§15.1): REVoi_bot.make_trades 호출·재구현0. 피처 전부 진입 직전 완성 4H봉(shift1·lookahead0).
#   ★비용: 슬립0=raw R(BASE 앵커 +1851.6491% 재현) · 현실=R−10bp×시장청산(memory#9·§19 헤드라인).
#   ★사이징=격리마진 강제청산(rauto_paper_engine 1:1). held-out=train≤2024 M20 사이징→test2025+ 채점(커닝0).
#   ★임계 er_thr=train(≤2024) 중앙ER 고정(test 누수0). CPCV 표준6=월6블록 choose2=15경로·purge±1M·폴드별 사이징 재선택.
import os, sys, json, itertools
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "08_BTC_Data")) and os.path.isdir(os.path.join(ROOT, "04_공용엔진코드")):
        break
    ROOT = os.path.dirname(ROOT)
RES = os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp")
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
sys.path.insert(0, RES)
from path_finder import ensure_paths
ensure_paths()
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from veri_edge import VeriEdge
import trendstack_signal_engine as TS
from rauto_cex import MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST

BASE = "260702_01_MicroRegimeWhip_Stg2_WhipLeverHoldoutCPCV"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", BASE)
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(WH, "00WorkHstr_INDEX.txt")
WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
ANCHOR = 1851.6491162901439
SLIP_REAL = 10.0 / 1e4                 # 현실 시장청산 슬립(memory#9)
LEVG = [3, 4, 5, 6, 8, 10, 13]
SZG = [50, 55, 65, 75, 85, 100]
W4 = 42                                 # 7일=42개 4H봉
ARMS = ["OFF", "L1_하락ER", "L2_랠리억제", "L3_저EV통합", "EX_조기익절강화"]


def _p(*a):
    print(*a, flush=True)


def market_mask(T):
    r = T["reason"].astype(str).str.lower() if "reason" in T else pd.Series(["fibstop"] * len(T))
    return (r.apply(lambda s: any(k in s for k in ("stop", "fib", "sl"))) | ~r.str.contains("tp|target|limit|early")).values


def R_series(T, real):
    R = T["R"].values.astype(float)
    if real:
        R = R - SLIP_REAL * market_mask(T).astype(float)
    return R


def entry_feat(T, d1m, rev_tf):
    """진입시점 causal 피처(shift1·lookahead0): ER(효율비)·trend(7일추세)·side."""
    et_ms = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000)
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    c4 = dfx["close"]
    ER = ((c4 - c4.shift(W4)).abs() / c4.diff().abs().rolling(W4).sum()).shift(1).values
    TR = ((c4 / c4.shift(W4) - 1.0) * 100.0).shift(1).values
    dfx_ms = (dfx.index.values.astype("int64") // 1_000_000)
    n = len(T); er = np.full(n, np.nan); tr = np.full(n, np.nan)
    for i in range(n):
        k = max(0, int(np.searchsorted(dfx_ms, et_ms[i], "right")) - 1)
        if k < len(ER):
            er[i] = ER[k]; tr[i] = TR[k]
    side = T["side"].astype(int).values
    return er, tr, side


def overlay_w(er, tr, side, arm, er_thr):
    n = len(er); w = np.ones(n)
    down_lowER = (tr <= -3) & (er < er_thr)
    rally_ctr = (tr >= 3) & (side == -1)
    if arm == "L1_하락ER":
        w[down_lowER] = 0.5
    elif arm == "L2_랠리억제":
        w[rally_ctr] = 0.5
    elif arm == "L3_저EV통합":
        w[down_lowER | rally_ctr] = 0.5
    return w


def metrics_on(idx, R, MAE, FUND, w, lev, sz, periods):
    """idx(시간순 거래) → 격리마진 사이징 → 거래단위 (tot%, mdd%, cagr%, 강제청산). (Stg4 1:1)"""
    if len(idx) == 0:
        return 0.0, 0.0, -100.0, 0
    exp0 = sz / 100.0 * lev; bal = 10000.0; peak = 10000.0; mdd = 0.0; nliq = 0
    Ri, Mi, Fi, wi = R[idx], MAE[idx], FUND[idx], w[idx]
    for i in range(len(idx)):
        if wi[i] <= 0:
            continue
        exp = exp0 * wi[i]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        if Mi[i] <= -hsd:
            pp = -exp * (hsd + LIQ_COST + abs(Fi[i])); nliq += 1
        else:
            pp = Ri[i] * exp
        bal *= (1.0 + pp); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
    tot = (bal / 1e4 - 1) * 100
    nmon = (periods[idx].max() - periods[idx].min()).n + 1
    cagr = ((bal / 1e4) ** (12.0 / max(nmon, 1)) - 1.0) * 100 if bal > 0 else -100.0
    return tot, mdd * 100, cagr, nliq


def monthly_pos(idx, R, MAE, FUND, w, lev, sz, periods):
    """idx 구간 월별 복리 → (양수월, 총월). floor(매월양수) 점검."""
    if len(idx) == 0:
        return 0, 0
    exp0 = sz / 100.0 * lev; bal = 10000.0
    Ri, Mi, Fi, wi, Pi = R[idx], MAE[idx], FUND[idx], w[idx], periods[idx]
    mfac = {}
    for i in range(len(idx)):
        if wi[i] <= 0:
            continue
        exp = exp0 * wi[i]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        pp = -exp * (hsd + LIQ_COST + abs(Fi[i])) if Mi[i] <= -hsd else Ri[i] * exp
        bal *= (1.0 + pp); mfac[Pi[i]] = mfac.get(Pi[i], 1.0) * (1.0 + pp)
    pos = sum(1 for v in mfac.values() if v > 1.0)
    return pos, len(mfac)


def pick_m20(idx, R, MAE, FUND, w, periods):
    """train서 M20(MDD≥-20) 만족 최대 CAGR 사이징. 없으면 최소MDD."""
    best = None; bestmdd = None
    for lev in LEVG:
        for sz in SZG:
            tot, mdd, cagr, nl = metrics_on(idx, R, MAE, FUND, w, lev, sz, periods)
            if mdd >= -20.0 and (best is None or cagr > best[2]):
                best = (lev, sz, cagr)
            if bestmdd is None or mdd > bestmdd[2]:
                bestmdd = (lev, sz, mdd)
    return (best[0], best[1]) if best else (bestmdd[0], bestmdd[1])


def build_arm_data(arm, p, combo_p, d1m, fund, rev_tf, er_thr_holder):
    """팔별 (R현실, R슬립0, MAE, FUND, w, periods, years, 거래수, er_thr). EX는 원장 재생성."""
    if arm == "EX_조기익절강화":
        params = {**combo_p, "early_tp_pct": 0.005}
        T = REVoiBot(params).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
        er, tr, side = entry_feat(T, d1m, rev_tf)
        w = np.ones(len(T))
    else:
        T = REVoiBot(combo_p).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
        er, tr, side = entry_feat(T, d1m, rev_tf)
        years = pd.to_datetime(T["et"]).dt.year.values
        if er_thr_holder[0] is None:
            er_thr_holder[0] = float(np.nanmedian(er[years <= 2024]))   # train 중앙ER 고정(누수0)
        w = overlay_w(er, tr, side, arm, er_thr_holder[0])
    Rr = R_series(T, real=True); Ro = R_series(T, real=False)
    MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    periods = pd.PeriodIndex(pd.to_datetime(T["et"]).dt.to_period("M"))
    years = pd.to_datetime(T["et"]).dt.year.values
    ncut = int((w < 1.0).sum())
    return dict(Rr=Rr, Ro=Ro, MAE=MAE, FUND=FUND, w=w, periods=periods, years=years, n=len(T), ncut=ncut)


def eval_arm(D):
    """held-out(현실) + CPCV 표준6(현실) + slip0 held-out(보조)."""
    Rr, Ro, MAE, FUND, w, periods, years = D["Rr"], D["Ro"], D["MAE"], D["FUND"], D["w"], D["periods"], D["years"]
    tr = np.where(years <= 2024)[0]; te = np.where(years >= 2025)[0]
    lev, sz = pick_m20(tr, Rr, MAE, FUND, w, periods)                     # 사이징=현실기준 train서 선택
    trtot, trmdd, _, _ = metrics_on(tr, Rr, MAE, FUND, w, lev, sz, periods)
    tetot, temdd, tecagr, tenl = metrics_on(te, Rr, MAE, FUND, w, lev, sz, periods)
    te0tot, te0mdd, _, _ = metrics_on(te, Ro, MAE, FUND, w, lev, sz, periods)  # slip0 보조
    pos, nmo = monthly_pos(te, Rr, MAE, FUND, w, lev, sz, periods)
    ho = dict(lev=lev, sz=sz, trtot=trtot, trmdd=trmdd, tetot=tetot, temdd=temdd,
              tecagr=tecagr, tenl=tenl, te0tot=te0tot, pos=pos, nmo=nmo)
    # CPCV 표준6
    cal = pd.period_range(periods.min(), periods.max(), freq="M")
    blocks = np.array_split(np.arange(len(cal)), 6)
    m2b = {}
    for bi, blk in enumerate(blocks):
        for mi in blk:
            m2b[cal[mi]] = bi
    tblk = np.array([m2b[per] for per in periods])
    cags = []; mdds = []
    for tb in itertools.combinations(range(6), 2):
        test_mask = np.isin(tblk, tb)
        purge = set()
        for b in tb:
            purge |= {b - 1, b + 1}
        train_mask = ~np.isin(tblk, list(set(tb) | purge))
        tri = np.where(train_mask)[0]; tei = np.where(test_mask)[0]
        if len(tri) < 30 or len(tei) < 10:
            continue
        lv, s = pick_m20(tri, Rr, MAE, FUND, w, periods)
        _, mdd, cagr, _ = metrics_on(tei, Rr, MAE, FUND, w, lv, s, periods)
        cags.append(cagr); mdds.append(mdd)
    cags = np.array(cags); mdds = np.array(mdds)
    cp = dict(p25=np.percentile(cags, 25), median=np.median(cags), neg=100 * (cags < 0).mean(),
              mdd_worst=mdds.min(), mdd_viol=100 * (mdds < -20).mean(), n=len(cags))
    return ho, cp


def make_graph(res, path):
    arms = list(res.keys())
    fig, ax = plt.subplots(1, 2, figsize=(15, 6))
    te = [res[a][0]["tetot"] for a in arms]
    p25 = [res[a][1]["p25"] for a in arms]
    viol = [res[a][1]["mdd_viol"] for a in arms]
    x = range(len(arms)); labs = [a.split("_")[0] for a in arms]
    c1 = ["#1a7f37" if v >= te[0] else "#c0392b" for v in te]
    ax[0].bar(x, te, color=c1); ax[0].axhline(te[0], color="gray", ls="--", lw=1)
    ax[0].set_xticks(x); ax[0].set_xticklabels(labs, rotation=20)
    ax[0].set_title("Held-out OOS test return (real, slip10bp) %\n(dashed=OFF baseline)")
    for i, v in enumerate(te):
        ax[0].text(i, v, f"{v:+.0f}", ha="center", va="bottom", fontsize=9)
    c2 = ["#1a7f37" if v <= viol[0] else "#c0392b" for v in viol]
    ax[1].bar(x, viol, color=c2); ax[1].axhline(viol[0], color="gray", ls="--", lw=1)
    ax[1].set_xticks(x); ax[1].set_xticklabels(labs, rotation=20)
    ax[1].set_title("CPCV std6 MDD<-20 violation %  (lower=better)\n(p25 annotated)")
    for i, (v, pp) in enumerate(zip(viol, p25)):
        ax[1].text(i, v, f"{v:.0f}%\np25={pp:+.0f}", ha="center", va="bottom", fontsize=8)
    fig.suptitle("Whipsaw 3-lever OOS test: which raises the floor without killing return", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(path, dpi=110); plt.close(fig)


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _p(f"[{BASE}] 휩소 3지렛대 정직검증 — held-out + CPCV 표준6 (COMBO 위 opt-in)")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    combo_p = {**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
    d1m = load_1m(); fund = load_funding(); rev_tf = int(p["rev_tf"])

    # ── 무손상 앵커 게이트(§15.2) ── BASE tp0/early0 lev3/75 슬립0 = +1851.6491%
    TB = REVoiBot(dict(p)).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    a = VeriEdge(TB).anchor_check(75, 3, ANCHOR, tol=1.0)
    _p(f"  [무손상] BASE lev3/75 슬립0 = {a['got_%']}% → {'✅ PASS' if a['pass'] else '❌ FAIL'}")
    if not a["pass"]:
        _p("  ❌ 앵커 불일치 → 검증 무효(§15.2). 중단."); return False

    er_thr_holder = [None]
    res = {}
    for arm in ARMS:
        D = build_arm_data(arm, p, combo_p, d1m, fund, rev_tf, er_thr_holder)
        ho, cp = eval_arm(D)
        res[arm] = (ho, cp, D)
        _p(f"  {arm:<16} 거래{D['n']}·축소{D['ncut']} · test현실 {ho['tetot']:+.0f}%/MDD{ho['temdd']:.0f}% · CPCV p25 {cp['p25']:+.0f}%·위반{cp['mdd_viol']:.0f}%")
    er_thr = er_thr_holder[0]

    # ── 보고(§19 헤드라인=OOS현실 수익률) ──
    L = []
    L.append("=" * 108)
    L.append(f"[휩소 3지렛대 정직검증 — held-out + CPCV 표준6] {BASE}")
    L.append("[성격] OOS 검증. 헤드라인=held-out OOS test 현실수익(슬립10bp·memory#6/#9). in-sample·천장 헤드라인 금지.")
    L.append(f"[무손상] BASE lev3/75 슬립0 = {a['got_%']}% = 앵커 +1851.6% 재현 ✅ · 임계 er_thr(train중앙ER) = {er_thr:.3f}")
    L.append("[지렛대] L1 하락&저ER×0.5 · L2 상승&숏(역주행)×0.5 · L3 둘다×0.5 [사이징오버레이·§25] · EX early_tp1.0→0.5%[청산·원장재생성]")
    L.append("[방법] 폴드별 train서 M20(MDD≥-20) 최대CAGR 사이징 재선택→보류 test 채점(커닝0·purge±1M). 비용 현실=R-10bp시장청산.")
    L.append("")
    L.append("[★① held-out (train≤2024 M20사이징 → test 2025+ = 진짜 OOS · 헤드라인=현실)]")
    L.append(f"{'지렛대':<16}{'train사이징':>11}{'test현실%':>11}{'testMDD':>9}{'test슬립0%':>11}{'연환산%':>9}{'매월양수':>9}{'강제청산':>8}")
    for arm in ARMS:
        ho = res[arm][0]
        szc = f"L{ho['lev']}/{ho['sz']}"
        L.append(f"{arm:<16}{szc:>11}{ho['tetot']:>+10.0f}%{ho['temdd']:>+8.0f}%{ho['te0tot']:>+10.0f}%{ho['tecagr']:>+8.0f}%"
                 f"{str(ho['pos'])+'/'+str(ho['nmo']):>9}{ho['tenl']:>8}")
    L.append("")
    L.append("[★② CPCV 표준6 (15경로·폴드별 재선택·purge — 본선 잣대 §5.7)]")
    L.append(f"{'지렛대':<16}{'p25(연%)':>10}{'중앙(연%)':>10}{'음수폴드%':>10}{'폴드MDD최악':>12}{'MDD-20위반%':>12}{'경로':>6}")
    for arm in ARMS:
        cp = res[arm][1]
        L.append(f"{arm:<16}{cp['p25']:>+9.0f}%{cp['median']:>+9.0f}%{cp['neg']:>9.0f}%{cp['mdd_worst']:>+11.0f}%{cp['mdd_viol']:>11.0f}%{cp['n']:>6}")
    L.append("")
    # 판정
    off_ho, off_cp = res["OFF"][0], res["OFF"][1]
    L.append("[★판정 — OFF(COMBO) 대비]")
    ranked = sorted([arm for arm in ARMS if arm != "OFF"],
                    key=lambda a: (res[a][1]["mdd_viol"], -res[a][0]["tetot"]))
    for arm in ARMS:
        if arm == "OFF":
            L.append(f"  · OFF(COMBO)     : test현실 {off_ho['tetot']:+.0f}%/MDD{off_ho['temdd']:.0f}% · CPCV p25 {off_cp['p25']:+.0f}%·위반 {off_cp['mdd_viol']:.0f}%·음수 {off_cp['neg']:.0f}% (기준)")
            continue
        ho, cp = res[arm][0], res[arm][1]
        dret = ho["tetot"] - off_ho["tetot"]; dviol = cp["mdd_viol"] - off_cp["mdd_viol"]
        verdict = "✅바닥↑(위반↓·수익유지)" if (dviol < 0 and dret > -off_ho["tetot"] * 0.3) else ("위반↓but수익↓" if dviol < 0 else ("수익↑" if dret > 0 else "개선없음"))
        L.append(f"  · {arm:<14}: test현실 {ho['tetot']:+.0f}%({dret:+.0f}) · MDD{ho['temdd']:.0f}% · CPCV p25 {cp['p25']:+.0f}%·위반 {cp['mdd_viol']:.0f}%({dviol:+.0f}p)·음수 {cp['neg']:.0f}% → {verdict}")
    best = ranked[0]
    pass_m20 = res[best][1]["p25"] > 0 and res[best][1]["mdd_viol"] == 0
    L.append("")
    L.append(f"  · ★최선(위반최소·수익차선) = {best} · M20 본선(p25>0·위반0) = {'통과' if pass_m20 else '미달'}")
    L.append("  · ★경계: 단일 지렛대로 위반0 미달이면 = 단일알파 한계 재확인(추세봇 상보 WO). in-sample·천장은 헤드라인 금지(§1).")
    body = "\n".join(L)

    # 저장
    rows_ho = [dict(지렛대=a, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in res[a][0].items()}) for a in ARMS]
    rows_cp = [dict(지렛대=a, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in res[a][1].items()}) for a in ARMS]
    pd.DataFrame(rows_ho).to_csv(os.path.join(OUTDIR, f"{BASE}_heldout.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(rows_cp).to_csv(os.path.join(OUTDIR, f"{BASE}_cpcv.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(OUTDIR, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    make_graph({a: (res[a][0], res[a][1]) for a in ARMS}, os.path.join(OUTDIR, f"{BASE}_지렛대비교.png"))
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|휩소 3지렛대 held-out+CPCV: "
                f"최선 {best}(위반{res[best][1]['mdd_viol']:.0f}%·test{res[best][0]['tetot']:+.0f}%) vs OFF(위반{off_cp['mdd_viol']:.0f}%·test{off_ho['tetot']:+.0f}%)·M20{'통과' if pass_m20 else '미달'}|src={BASE}.py\n")
    _p("\n" + body)
    _p(f"\n[저장] {OUTDIR}\\  · heldout.csv · cpcv.csv · 분석.txt · 지렛대비교.png")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
