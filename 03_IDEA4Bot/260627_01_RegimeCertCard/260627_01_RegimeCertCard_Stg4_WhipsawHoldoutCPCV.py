# -*- coding: utf-8 -*-
# [260627_01_RegimeCertCard_Stg4_WhipsawHoldoutCPCV] ★휩소 오버레이 정직검증 — held-out + CPCV 표준6 (세션 260627_01_RegimeCertCard).
#   캡틴 "1 이후 2": Stg3 WHIP_soft(+8657% M20, in-sample 천장)가 미래참조 없는 OOS서도 살아남나?
#   방법(§5.7·§15): R+P70 베이스 고정 · OFF vs WHIP_soft 두 팔 · 사이즈드 CPCV(폴드별 train서 M20 사이징 재선택→보류 test 채점·purge).
#   ① held-out: train≤2024서 M20 최대수익 사이징 → test 2025~26 적용(커닝0). ② CPCV 표준6 15경로 OOS p25·MDD-20위반·음수폴드.
#   ★전부 lookahead0(진입피처 et 과거값). 비용=§24 RautoCEX 현실. 무손상=OFF lev6/55=+8669%(Stg1 카드).
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
import trendstack_signal_engine as TS
from rauto_cex import FeeModel, SlipModel, MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST, MK, TK

WINNERS = os.path.join(RES, "back2tv_rev_winners.json")
BASE = "260627_04_WhipsawHoldoutCPCV"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output")
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(ROOT, "00_WorkHstr", "00WorkHstr_INDEX.txt")
LEVG = [3, 4, 5, 6, 8, 10, 13]
SZG = [50, 55, 65, 75, 85, 100]
QW, ZW = 0.30, 1.0   # WHIP_soft 임계(저변동 ATR≤Q30, OI충격 |oi_z|≥1.0) — Stg3 최선


def _p(*a):
    print(*a, flush=True)


def make_ledger(p, tp_frac, regime_factor, gate, d1m, fund):
    params = dict(p); params["tp_frac"] = tp_frac; params["regime_factor"] = regime_factor; params["gate"] = gate
    return REVoiBot(params).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)


def cost_real(T):
    R = T["R"].values.astype(float); F = T["fund"].values.astype(float)
    REA = T["reason"].values if "reason" in T else np.array(["fibstop"] * len(R))
    fee = FeeModel(); sl = SlipModel(0.0, 1.0).market_exit_slip()
    return np.array([R[i] + MK + TK + F[i] - fee.entry_cost(False) - fee.exit_cost(REA[i]) - F[i]
                     - (sl if REA[i] != "tp" else 0.0) for i in range(len(R))])


def entry_features(T, d1m, rev_tf):
    et_ms = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000).astype("int64")
    mt = (d1m.index.values.astype("int64") // 1_000_000).astype("int64")
    oiz_arr = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce").values
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    tr = (dfx["high"] - dfx["low"]) / dfx["close"]
    atrp = tr.rolling(14, min_periods=5).mean().rolling(720, min_periods=120).rank(pct=True).values
    dfx_ms = (dfx.index.values.astype("int64") // 1_000_000).astype("int64")
    n = len(T); oiz = np.zeros(n); apct = np.full(n, 0.5)
    for i in range(n):
        j = max(0, int(np.searchsorted(mt, et_ms[i], "right")) - 1)
        oiz[i] = oiz_arr[j] if not np.isnan(oiz_arr[j]) else 0.0
        k = max(0, int(np.searchsorted(dfx_ms, et_ms[i], "right")) - 1)
        apct[i] = atrp[k] if (k < len(atrp) and not np.isnan(atrp[k])) else 0.5
    return apct, oiz


def overlay_w(apct, oiz, arm):
    w = np.ones(len(apct))
    if arm == "WHIP_soft":
        w[(apct <= QW) & (np.abs(oiz) >= ZW)] = 0.5
    return w


def sized_p(Rc, MAE, FUND, lev, sz, w):
    """부분집합 격리마진 사이징 → per-trade p, 강제청산수. (시간순 입력 전제)"""
    exp0 = sz / 100.0 * lev; bal = 10000.0; p = np.zeros(len(Rc)); nliq = 0
    for i in range(len(Rc)):
        if w[i] <= 0:
            continue
        exp = exp0 * w[i]; mmr = MMR_T2 if exp * bal > TIER else MMR_T1; hsd = 1.0 / lev - mmr - LIQ_SLIP
        if MAE[i] <= -hsd:
            pp = -exp * (hsd + LIQ_COST + abs(FUND[i])); nliq += 1
        else:
            pp = Rc[i] * exp
        bal *= (1.0 + pp); p[i] = pp
    return p, nliq


def cmdd(m):
    m = np.asarray(m, float)
    if len(m) == 0:
        return 0.0, 0.0, -100.0
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = np.min((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)) * 100
    yrs = len(m) / 12.0
    cagr = ((eq[-1]) ** (1 / yrs) - 1) * 100 if (yrs > 0 and eq[-1] > 0) else -100.0
    return tot, mdd, cagr


def metrics_on(idx, Rc, MAE, FUND, w, lev, sz, periods):
    """idx(시간순 거래) → 사이즈드 ★거래단위 MDD(Stg3·§26 일치) → (tot%, mdd%, cagr%, 강제청산)."""
    if len(idx) == 0:
        return 0.0, 0.0, -100.0, 0
    p, nliq = sized_p(Rc[idx], MAE[idx], FUND[idx], lev, sz, w[idx])
    bal = 10000.0; peak = 10000.0; mdd = 0.0
    for x in p:
        bal *= (1.0 + x); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
    tot = (bal / 1e4 - 1) * 100
    nmon = (periods[idx].max() - periods[idx].min()).n + 1
    yrs = max(nmon / 12.0, 1e-6)
    cagr = ((bal / 1e4) ** (1.0 / yrs) - 1.0) * 100 if bal > 0 else -100.0
    return tot, mdd * 100, cagr, nliq


def pick_m20(idx, Rc, MAE, FUND, w, periods):
    """train 구간서 M20(MDD≥-20) 만족 최대 CAGR 사이징. 없으면 최소MDD."""
    best = None; bestmdd = None
    for lev in LEVG:
        for sz in SZG:
            tot, mdd, cagr, nl = metrics_on(idx, Rc, MAE, FUND, w, lev, sz, periods)
            if mdd >= -20.0 and (best is None or cagr > best[2]):
                best = (lev, sz, cagr)
            if bestmdd is None or mdd > bestmdd[2]:
                bestmdd = (lev, sz, mdd)
    return (best[0], best[1]) if best else (bestmdd[0], bestmdd[1])


def main():
    _p(f"[{BASE}] 휩소 오버레이 정직검증 — held-out + CPCV 표준6 (OFF vs WHIP_soft)")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = make_ledger(p, 0.7, 1.0, False, d1m, fund)
    Rc = cost_real(T); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    apct, oiz = entry_features(T, d1m, int(p["rev_tf"]))
    periods = pd.PeriodIndex(pd.to_datetime(T["et"]).dt.to_period("M"))
    years = pd.to_datetime(T["et"]).dt.year.values
    arms = {"OFF": overlay_w(apct, oiz, "OFF"), "WHIP_soft": overlay_w(apct, oiz, "WHIP_soft")}
    nwhip = int(((apct <= QW) & (np.abs(oiz) >= ZW)).sum())
    _p(f"  베이스 R+P70 {len(T)}거래 · 휩소축소(저변동&OI충격) {nwhip}건({100*nwhip/len(T):.0f}%)")
    # 무손상
    t0, m0, _, _ = metrics_on(np.arange(len(T)), Rc, MAE, FUND, arms["OFF"], 6, 55, periods)
    _p(f"  [무손상] OFF lev6/55 = {t0:+.0f}%/MDD{m0:.0f}% (Stg1 +8669%/-21% 기대)")
    if abs(t0 - 8669) > 200:
        _p("  ❌ 무손상 경고 — 중단."); return False

    allidx = np.arange(len(T))
    # ── ① held-out: train≤2024 M20 사이징 → test 2025~26 ──
    tr = np.where(years <= 2024)[0]; te = np.where(years >= 2025)[0]
    ho = {}
    for arm, w in arms.items():
        lev, sz = pick_m20(tr, Rc, MAE, FUND, w, periods)
        trtot, trmdd, _, _ = metrics_on(tr, Rc, MAE, FUND, w, lev, sz, periods)
        tetot, temdd, tecagr, tenl = metrics_on(te, Rc, MAE, FUND, w, lev, sz, periods)
        ho[arm] = dict(lev=lev, sz=sz, trtot=trtot, trmdd=trmdd, tetot=tetot, temdd=temdd, tecagr=tecagr, tenl=tenl)

    # ── ② CPCV 표준6 (월 6블록 choose-2=15경로, purge 1개월) ──
    cal = pd.period_range(periods.min(), periods.max(), freq="M")
    blocks = np.array_split(np.arange(len(cal)), 6)
    m2b = {}
    for bi, blk in enumerate(blocks):
        for mi in blk:
            m2b[cal[mi]] = bi
    tblk = np.array([m2b[per] for per in periods])
    cpcv = {}
    for arm, w in arms.items():
        cags = []; mdds = []
        for tb in itertools.combinations(range(6), 2):
            test_mask = np.isin(tblk, tb)
            # purge: test 블록 경계 ±1개월 train서 제외(embargo)
            test_blocks = set(tb); purge = set()
            for b in tb:
                purge |= {b - 1, b + 1}
            train_mask = ~np.isin(tblk, list(test_blocks | purge))
            tri = np.where(train_mask)[0]; tei = np.where(test_mask)[0]
            if len(tri) < 30 or len(tei) < 10:
                continue
            lev, sz = pick_m20(tri, Rc, MAE, FUND, w, periods)
            _, mdd, cagr, _ = metrics_on(tei, Rc, MAE, FUND, w, lev, sz, periods)
            cags.append(cagr); mdds.append(mdd)
        cags = np.array(cags); mdds = np.array(mdds)
        cpcv[arm] = dict(p25=np.percentile(cags, 25), median=np.median(cags), neg=100 * (cags < 0).mean(),
                         mdd_worst=mdds.min(), mdd_viol=100 * (mdds < -20).mean(), n=len(cags))

    # ── 보고 ──
    L = []
    L.append(f"[휩소 오버레이 정직검증 — held-out + CPCV 표준6] {BASE}")
    L.append("[방법] R+P70 베이스 고정 · OFF vs WHIP_soft(저변동&OI충격 사이즈0.5) · 폴드별 train서 M20(MDD≥-20) 최대수익 사이징 재선택→보류 test 채점(커닝0·purge1M).")
    L.append(f"[휩소축소 대상] 저변동(ATR≤Q{int(QW*100)})&OI충격(|oi_z|≥{ZW}) 동시 = {100*nwhip/len(T):.0f}% 진입.")
    L.append("")
    L.append("[★① held-out (train≤2024 최적 → test 2025~26, 진짜 OOS)]")
    L.append(f"{'팔':<12}{'train사이징':>12}{'train수익/MDD':>18}{'★test수익':>12}{'testMDD':>9}{'test연환산':>11}{'강제청산':>8}")
    for arm in ["OFF", "WHIP_soft"]:
        h = ho[arm]
        szc = "L{}/{}".format(int(h["lev"]), int(h["sz"]))
        trc = "{:+.0f}%/{:.0f}%".format(h["trtot"], h["trmdd"])
        L.append(f"{arm:<12}{szc:>12}{trc:>18}{h['tetot']:>+11.0f}%{h['temdd']:>+8.0f}%{h['tecagr']:>+10.0f}%{h['tenl']:>8}")
    L.append("")
    L.append("[★② CPCV 표준6 (15경로·재선택·purge — 본선 잣대)]")
    L.append(f"{'팔':<12}{'p25(연%)':>10}{'중앙(연%)':>10}{'음수폴드%':>10}{'폴드MDD최악':>12}{'MDD-20위반%':>12}{'경로':>6}")
    for arm in ["OFF", "WHIP_soft"]:
        c = cpcv[arm]
        L.append(f"{arm:<12}{c['p25']:>+9.0f}%{c['median']:>+9.0f}%{c['neg']:>9.0f}%{c['mdd_worst']:>+11.0f}%{c['mdd_viol']:>11.0f}%{c['n']:>6}")
    L.append("")
    # 판정
    wo = ho["WHIP_soft"]; of = ho["OFF"]; cw = cpcv["WHIP_soft"]; co = cpcv["OFF"]
    ho_better = wo["tetot"] > of["tetot"]
    cpcv_better = (cw["p25"] >= co["p25"]) and (cw["mdd_viol"] <= co["mdd_viol"])
    pass_m20 = cw["p25"] > 0 and cw["mdd_viol"] == 0
    L.append("[판정]")
    L.append(f"  · held-out OOS: WHIP_soft test {wo['tetot']:+.0f}%/MDD{wo['temdd']:.0f}% vs OFF {of['tetot']:+.0f}%/MDD{of['temdd']:.0f}% → WHIP_soft {'우위' if ho_better else '열위'}")
    L.append(f"  · CPCV 표준6: WHIP_soft p25 {cw['p25']:+.0f}%·위반 {cw['mdd_viol']:.0f}% vs OFF p25 {co['p25']:+.0f}%·위반 {co['mdd_viol']:.0f}% → WHIP_soft {'우위' if cpcv_better else '열위/동등'}")
    L.append(f"  · ★M20 본선(p25>0·MDD-20위반0): WHIP_soft = {'통과' if pass_m20 else '미달'}")
    L.append(f"  · 결론: 휩소 오버레이는 OOS서 {'유효(채택 후보·held-out·CPCV 둘 다 OFF 대비 개선)' if (ho_better and cpcv_better) else '미검증/부분(헛수치 위 쌓기 금지 — in-sample +8657%는 천장)'}.")
    body = "\n".join(L)

    folder = os.path.join(OUTDIR, BASE); os.makedirs(folder, exist_ok=True)
    pd.DataFrame([dict(팔=a, **{k: round(v, 1) if isinstance(v, float) else v for k, v in ho[a].items()}) for a in ho]).to_csv(
        os.path.join(folder, f"{BASE}_heldout.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame([dict(팔=a, **{k: round(v, 1) if isinstance(v, float) else v for k, v in cpcv[a].items()}) for a in cpcv]).to_csv(
        os.path.join(folder, f"{BASE}_cpcv.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(folder, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    ts = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|휩소 오버레이 정직검증: "
                f"held-out WHIP_soft {wo['tetot']:+.0f}% vs OFF {of['tetot']:+.0f}% · CPCV p25 {cw['p25']:+.0f}%/위반{cw['mdd_viol']:.0f}% vs OFF p25 {co['p25']:+.0f}%/위반{co['mdd_viol']:.0f}% · M20본선 {'통과' if pass_m20 else '미달'}|src={BASE}.py\n")
    _p("\n" + body)
    _p(f"\n[저장] {folder}\\  · heldout.csv · cpcv.csv · 분석.txt")
    return True


if __name__ == "__main__":
    main()
