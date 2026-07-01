# -*- coding: utf-8 -*-
# [260702_01_MicroRegimeWhip_Stg3_L2RallyRefine] ★L2 랠리억제 정밀화 — 최종 스펙 확정 (세션 260702_01_MicroRegimeWhip).
#   Stg2 결론: L2(상승&숏 역주행 ×0.5)가 held-out OOS 수익 2배(+1058→+2155%)·최선. 단 CPCV MDD-20위반 57%(=단일알파 한계).
#   캡틴 지시: L2 정밀화 → 결정두뇌 반영. 이 Stg = 정밀화(순수분석·엔진변경0·앵커 무관):
#     ① 강도 민감도: ×0.5 / ×0.3 / skip(×0) — 얼마나 줄일지.
#     ② 임계 민감도: 상승 trend≥+2 / +3 / +5 — 얼마나 강한 랠리부터.
#     ③ 대칭성: 랠리숏만(비대칭) vs 랠리숏+급락롱(대칭) — Stg1대로 급락롱은 REVoi 강점이라 대칭은 나쁠 것(확증).
#     ④ ★같은 위험(고정 사이징)서 L2가 바닥/MDD를 올리나 = 순수 리스크효과 분리(사이징 재선택 없이).
#     ⑤ ★매월양수 100% 타진: L2 최선안이 test서 전월양수 되는 사이징 존재하나(§0 목표).
#   ★검증엔진만(§8·§15.1)·causal 피처(shift1·lookahead0)·비용 현실=R−10bp시장청산(memory#9)·무손상 앵커 게이트.
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
from fib_replay_1m import load_1m, load_funding
from REVoi_bot import REVoiBot
from veri_edge import VeriEdge
import trendstack_signal_engine as TS
from rauto_cex import MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST

BASE = "260702_01_MicroRegimeWhip_Stg3_L2RallyRefine"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output", BASE)
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(WH, "00WorkHstr_INDEX.txt")
WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
ANCHOR = 1851.6491162901439
SLIP_REAL = 10.0 / 1e4
LEVG = [3, 4, 5, 6, 8, 10, 13]
SZG = [50, 55, 65, 75, 85, 100]
W4 = 42
FIXLEV, FIXSZ = 4, 75          # ④ 같은위험 고정 사이징(보수)


def _p(*a):
    print(*a, flush=True)


def market_mask(T):
    r = T["reason"].astype(str).str.lower()
    return (r.apply(lambda s: any(k in s for k in ("stop", "fib", "sl"))) | ~r.str.contains("tp|target|limit|early")).values


def R_series(T, real):
    R = T["R"].values.astype(float)
    return R - SLIP_REAL * market_mask(T).astype(float) if real else R


def entry_feat(T, d1m, rev_tf):
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
    return er, tr, T["side"].astype(int).values


def make_w(er, tr, side, thr, factor, symmetric):
    w = np.ones(len(er))
    rally_short = (tr >= thr) & (side == -1)
    w[rally_short] = factor
    if symmetric:
        w[(tr <= -thr) & (side == 1)] = factor    # 급락롱도 대칭축소(가설검증용)
    return w


def metrics_on(idx, R, MAE, FUND, w, lev, sz, periods):
    if len(idx) == 0:
        return 0.0, 0.0, -100.0, 0
    exp0 = sz / 100.0 * lev; bal = peak = 10000.0; mdd = 0.0; nliq = 0
    Ri, Mi, Fi, wi = R[idx], MAE[idx], FUND[idx], w[idx]
    for i in range(len(idx)):
        if wi[i] <= 0:
            continue
        exp = exp0 * wi[i]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        pp = -exp * (hsd + LIQ_COST + abs(Fi[i])) if Mi[i] <= -hsd else Ri[i] * exp
        bal *= (1.0 + pp); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
        if Mi[i] <= -hsd:
            nliq += 1
    tot = (bal / 1e4 - 1) * 100
    nmon = (periods[idx].max() - periods[idx].min()).n + 1
    cagr = ((bal / 1e4) ** (12.0 / max(nmon, 1)) - 1.0) * 100 if bal > 0 else -100.0
    return tot, mdd * 100, cagr, nliq


def monthly_pos(idx, R, MAE, FUND, w, lev, sz, periods):
    if len(idx) == 0:
        return 0, 0
    exp0 = sz / 100.0 * lev; bal = 10000.0; mfac = {}
    Ri, Mi, Fi, wi, Pi = R[idx], MAE[idx], FUND[idx], w[idx], periods[idx]
    for i in range(len(idx)):
        if wi[i] <= 0:
            continue
        exp = exp0 * wi[i]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        pp = -exp * (hsd + LIQ_COST + abs(Fi[i])) if Mi[i] <= -hsd else Ri[i] * exp
        bal *= (1.0 + pp); mfac[Pi[i]] = mfac.get(Pi[i], 1.0) * (1.0 + pp)
    return sum(1 for v in mfac.values() if v > 1.0), len(mfac)


def pick_m20(idx, R, MAE, FUND, w, periods):
    best = None; bestmdd = None
    for lev in LEVG:
        for sz in SZG:
            _, mdd, cagr, _ = metrics_on(idx, R, MAE, FUND, w, lev, sz, periods)
            if mdd >= -20.0 and (best is None or cagr > best[2]):
                best = (lev, sz, cagr)
            if bestmdd is None or mdd > bestmdd[2]:
                bestmdd = (lev, sz, mdd)
    return (best[0], best[1]) if best else (bestmdd[0], bestmdd[1])


def cpcv_blocks(periods):
    cal = pd.period_range(periods.min(), periods.max(), freq="M")
    blocks = np.array_split(np.arange(len(cal)), 6)
    m2b = {}
    for bi, blk in enumerate(blocks):
        for mi in blk:
            m2b[cal[mi]] = bi
    return np.array([m2b[per] for per in periods])


def cpcv_retune(R, MAE, FUND, w, periods, tblk):
    """폴드별 train서 M20 사이징 재선택 → test 채점(Stg2 본선)."""
    cags = []; mdds = []
    for tb in itertools.combinations(range(6), 2):
        tei = np.where(np.isin(tblk, tb))[0]
        purge = set()
        for b in tb:
            purge |= {b - 1, b + 1}
        tri = np.where(~np.isin(tblk, list(set(tb) | purge)))[0]
        if len(tri) < 30 or len(tei) < 10:
            continue
        lv, s = pick_m20(tri, R, MAE, FUND, w, periods)
        _, mdd, cagr, _ = metrics_on(tei, R, MAE, FUND, w, lv, s, periods)
        cags.append(cagr); mdds.append(mdd)
    cags = np.array(cags); mdds = np.array(mdds)
    return dict(p25=np.percentile(cags, 25), median=np.median(cags), neg=100 * (cags < 0).mean(),
                mdd_viol=100 * (mdds < -20).mean(), n=len(cags))


def cpcv_fixed(R, MAE, FUND, w, periods, tblk, lev, sz):
    """④ 고정 사이징(재선택0)으로 15경로 test — 순수 리스크효과(같은위험)."""
    cags = []; mdds = []
    for tb in itertools.combinations(range(6), 2):
        tei = np.where(np.isin(tblk, tb))[0]
        if len(tei) < 10:
            continue
        _, mdd, cagr, _ = metrics_on(tei, R, MAE, FUND, w, lev, sz, periods)
        cags.append(cagr); mdds.append(mdd)
    cags = np.array(cags); mdds = np.array(mdds)
    return dict(p25=np.percentile(cags, 25), median=np.median(cags), mdd_viol=100 * (mdds < -20).mean(),
                mdd_worst=mdds.min(), n=len(cags))


def floor_sizing(idx, R, MAE, FUND, w, periods):
    """⑤ test서 매월양수 100% 되는 사이징 중 최대수익 + 그 MDD. 없으면 최다양수."""
    best = None; bestpos = None
    for lev in LEVG:
        for sz in SZG:
            tot, mdd, _, _ = metrics_on(idx, R, MAE, FUND, w, lev, sz, periods)
            pos, nmo = monthly_pos(idx, R, MAE, FUND, w, lev, sz, periods)
            if nmo == 0:
                continue
            if pos == nmo and (best is None or tot > best[0]):
                best = (tot, mdd, lev, sz, pos, nmo)
            if bestpos is None or (pos / nmo, tot) > (bestpos[4] / bestpos[5], bestpos[0]):
                bestpos = (tot, mdd, lev, sz, pos, nmo)
    return best if best else bestpos, best is not None


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    _p(f"[{BASE}] L2 랠리억제 정밀화 — 강도·임계·대칭성·고정위험·매월양수")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    combo_p = {**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
    d1m = load_1m(); fund = load_funding(); rev_tf = int(p["rev_tf"])

    # 무손상
    TB = REVoiBot(dict(p)).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    a = VeriEdge(TB).anchor_check(75, 3, ANCHOR, tol=1.0)
    _p(f"  [무손상] BASE lev3/75 슬립0 = {a['got_%']}% → {'✅ PASS' if a['pass'] else '❌ FAIL'}")
    if not a["pass"]:
        _p("  ❌ 중단(§15.2)."); return False

    # COMBO 원장 1회 + 피처
    T = REVoiBot(combo_p).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    er, tr, side = entry_feat(T, d1m, rev_tf)
    Rr = R_series(T, True); Ro = R_series(T, False)
    MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    periods = pd.PeriodIndex(pd.to_datetime(T["et"]).dt.to_period("M"))
    years = pd.to_datetime(T["et"]).dt.year.values
    tblk = cpcv_blocks(periods)
    tr_idx = np.where(years <= 2024)[0]; te_idx = np.where(years >= 2025)[0]

    # 변형 정의
    VARS = {
        "OFF": (None, 1.0, False),
        "L2_x0.5(+3)": (3, 0.5, False),      # Stg2 승자
        "L2_x0.3(+3)": (3, 0.3, False),
        "L2_skip(+3)":  (3, 0.0, False),
        "L2_x0.5(+2)": (2, 0.5, False),
        "L2_x0.5(+5)": (5, 0.5, False),
        "L2_sym(+3)":   (3, 0.5, True),       # 대칭(급락롱도 축소=나쁠 것)
    }
    res = {}
    for nm, (thr, fac, sym) in VARS.items():
        w = np.ones(len(T)) if thr is None else make_w(er, tr, side, thr, fac, sym)
        lev, sz = pick_m20(tr_idx, Rr, MAE, FUND, w, periods)
        tetot, temdd, _, tenl = metrics_on(te_idx, Rr, MAE, FUND, w, lev, sz, periods)
        pos, nmo = monthly_pos(te_idx, Rr, MAE, FUND, w, lev, sz, periods)
        cp = cpcv_retune(Rr, MAE, FUND, w, periods, tblk)
        ncut = int((w < 1.0).sum())
        res[nm] = dict(lev=lev, sz=sz, tetot=tetot, temdd=temdd, tenl=tenl, pos=pos, nmo=nmo, ncut=ncut, **{f"cp_{k}": v for k, v in cp.items()})
        _p(f"  {nm:<14} 축소{ncut} · test {tetot:+.0f}%/MDD{temdd:.0f}% 양수{pos}/{nmo} · CPCV p25 {cp['p25']:+.0f}%·위반{cp['mdd_viol']:.0f}%")

    # ④ 같은위험 고정사이징(L{FIXLEV}/{FIXSZ}) — OFF vs L2_x0.5(+3) 순수 리스크효과
    w_off = np.ones(len(T)); w_l2 = make_w(er, tr, side, 3, 0.5, False)
    fix = {}
    for nm, w in [("OFF", w_off), ("L2_x0.5(+3)", w_l2)]:
        ho_tot, ho_mdd, _, _ = metrics_on(te_idx, Rr, MAE, FUND, w, FIXLEV, FIXSZ, periods)
        pos, nmo = monthly_pos(te_idx, Rr, MAE, FUND, w, FIXLEV, FIXSZ, periods)
        cf = cpcv_fixed(Rr, MAE, FUND, w, periods, tblk, FIXLEV, FIXSZ)
        fix[nm] = dict(tot=ho_tot, mdd=ho_mdd, pos=pos, nmo=nmo, **cf)

    # ⑤ 매월양수 100% 타진 (L2_x0.5(+3), test)
    fs, ok100 = floor_sizing(te_idx, Rr, MAE, FUND, w_l2, periods)

    # ── 보고 ──
    L = []
    L.append("=" * 104)
    L.append(f"[L2 랠리억제 정밀화 — 최종 스펙] {BASE}")
    L.append("[성격] 정밀화(엔진변경0). 헤드라인=held-out OOS test 현실(슬립10bp·memory#6/#9). CPCV 표준6=본선.")
    L.append(f"[무손상] BASE lev3/75 슬립0 = {a['got_%']}% = 앵커 재현 ✅")
    L.append("")
    L.append("[① 강도·임계·대칭 민감도 — held-out OOS(train≤2024 M20사이징→test2025+) + CPCV]")
    L.append(f"{'변형':<14}{'축소수':>6}{'사이징':>9}{'test현실%':>10}{'MDD':>7}{'매월양수':>8}{'CPCVp25':>9}{'위반%':>7}")
    for nm in VARS:
        r = res[nm]
        L.append(f"{nm:<14}{r['ncut']:>6}{'L'+str(r['lev'])+'/'+str(r['sz']):>9}{r['tetot']:>+9.0f}%{r['temdd']:>+6.0f}%"
                 f"{str(r['pos'])+'/'+str(r['nmo']):>8}{r['cp_p25']:>+8.0f}%{r['cp_mdd_viol']:>6.0f}%")
    L.append("")
    L.append(f"[④ 같은위험(고정 L{FIXLEV}/{FIXSZ}) — 순수 리스크효과: L2가 같은 레버서 MDD/바닥 개선하나]")
    L.append(f"{'':<14}{'test현실%':>10}{'testMDD':>9}{'매월양수':>8}{'CPCV p25':>10}{'CPCV위반%':>10}{'폴드MDD최악':>12}")
    for nm in ["OFF", "L2_x0.5(+3)"]:
        f = fix[nm]
        L.append(f"{nm:<14}{f['tot']:>+9.0f}%{f['mdd']:>+8.0f}%{str(f['pos'])+'/'+str(f['nmo']):>8}{f['p25']:>+9.0f}%{f['mdd_viol']:>9.0f}%{f['mdd_worst']:>+11.0f}%")
    dviol = fix["L2_x0.5(+3)"]["mdd_viol"] - fix["OFF"]["mdd_viol"]
    dmdd = fix["L2_x0.5(+3)"]["mdd"] - fix["OFF"]["mdd"]
    L.append(f"   → 같은 L{FIXLEV}/{FIXSZ}서 L2: CPCV위반 {dviol:+.0f}p · held-out MDD {dmdd:+.0f}p (음수=개선)")
    L.append("")
    L.append(f"[⑤ 매월양수 100% 타진 (L2_x0.5(+3)·test 2025+)]")
    if ok100:
        L.append(f"   ✅ 전월양수 사이징 존재 = L{fs[2]}/{fs[3]} → test {fs[0]:+.0f}%/MDD{fs[1]:.0f}% ({fs[4]}/{fs[5]}월)")
    else:
        L.append(f"   ✗ 전월양수 사이징 없음 → 최다 = L{fs[2]}/{fs[3]} {fs[4]}/{fs[5]}월 · test {fs[0]:+.0f}%/MDD{fs[1]:.0f}% (2개월 이하 음수 잔존)")
    L.append("")
    # 판정
    off = res["OFF"]; l2 = res["L2_x0.5(+3)"]
    # 최선 = CPCV MDD-20위반 최소 → 그 중 test수익 최대 (수익만 보면 skip이 레버업으로 위반↑=함정)
    cand = sorted([n for n in VARS if n != "OFF"], key=lambda n: (res[n]["cp_mdd_viol"], -res[n]["tetot"]))
    best = cand[0]
    ret_top = max((n for n in VARS if n != "OFF"), key=lambda n: res[n]["tetot"])
    L.append("[★판정]")
    L.append(f"  · 균형 최선(위반최소→수익최대) = {best} (test {res[best]['tetot']:+.0f}%/위반{res[best]['cp_mdd_viol']:.0f}% vs OFF {off['tetot']:+.0f}%/위반{off['cp_mdd_viol']:.0f}%)")
    L.append(f"  · ★수익최대는 {ret_top}(test {res[ret_top]['tetot']:+.0f}%)지만 위반{res[ret_top]['cp_mdd_viol']:.0f}%(레버업 함정) — 수익만 보면 안 됨.")
    L.append(f"  · 강도: ×0.5 vs ×0.3 vs skip → {res['L2_x0.5(+3)']['tetot']:+.0f}% / {res['L2_x0.3(+3)']['tetot']:+.0f}% / {res['L2_skip(+3)']['tetot']:+.0f}% (skip 과하면 EV손실)")
    L.append(f"  · 임계: +2/+3/+5 → {res['L2_x0.5(+2)']['tetot']:+.0f}% / {res['L2_x0.5(+3)']['tetot']:+.0f}% / {res['L2_x0.5(+5)']['tetot']:+.0f}%")
    L.append(f"  · 대칭성: 대칭(급락롱도축소) {res['L2_sym(+3)']['tetot']:+.0f}% vs 비대칭 {l2['tetot']:+.0f}% → {'비대칭 우위(급락롱=REVoi 강점, 축소 금지 확증)' if l2['tetot'] > res['L2_sym(+3)']['tetot'] else '재검토'}")
    L.append(f"  · ★같은위험 리스크효과: L2가 고정 L{FIXLEV}/{FIXSZ}서 CPCV위반 {dviol:+.0f}p → {'같은레버서도 MDD 개선(사이징여유+리스크↓ 둘다)' if dviol < 0 else '같은레버선 MDD 개선 미미(효과는 사이징여유 위주)'}")
    L.append(f"  · ★매월양수 100% = {'달성 사이징 존재' if ok100 else '미달(2개월↓ 음수 잔존 = 추세봇 상보 필요)'}")
    L.append("  · ★경계: MDD-20 챔피언 인증은 여전히 추세봇 상보 필요(Stg2 4차확인). L2는 '수익 바닥↑ + 리스크↓'의 실물 지렛대(결정두뇌 반영 후보).")
    body = "\n".join(L)

    pd.DataFrame([dict(변형=n, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in res[n].items()}) for n in VARS]).to_csv(
        os.path.join(OUTDIR, f"{BASE}_민감도.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame([dict(사이징=n, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in fix[n].items()}) for n in fix]).to_csv(
        os.path.join(OUTDIR, f"{BASE}_고정위험.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(OUTDIR, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|L2 랠리억제 정밀화: "
                f"최선 {best}(test{res[best]['tetot']:+.0f}%) · 같은위험 CPCV위반 {dviol:+.0f}p · 매월양수100% {'달성' if ok100 else '미달'}|src={BASE}.py\n")
    _p("\n" + body)
    _p(f"\n[저장] {OUTDIR}\\  · 민감도.csv · 고정위험.csv · 분석.txt")
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
