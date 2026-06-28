# -*- coding: utf-8 -*-
# [260627_01_RegimeCertCard_Stg5_LeverBlendMDD20] ★레버 배합(휩소+진입품질) — §26 4단 천장 + OOS CPCV (세션 260627_01_RegimeCertCard).
#   캡틴 지침: "MDD-20 통과는 의미있지만 이걸로 가능성을 싹 자르지 마라. 알파 아이디어 아직 많고 휩소도 그중 하나."
#   → 배합별 §26 4단 최대수익(M0/M30/M25/M20=가능성 천장)을 '먼저' 다 보여주고, OOS CPCV MDD-20위반은 '보조'(이분법 금지).
#   레버(전부 size×0.5·lookahead0): W=저변동&OI충격 · G=추세역행 · S2=강OI충격(|z|≥2) · SK=극단 롱숏쏠림.
#   ★검증엔진 무수정 호출. 비용=§24 RautoCEX 현실. 거래단위 MDD(Stg3/4·§26 일치). 무손상=OFF lev6/55 +8669%.
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
REG = os.path.join(ROOT, "08_BTC_Data", "derived", "_regime_features.parquet")
BASE = "260627_05_LeverBlendMDD20"
OUTDIR = os.path.join(ROOT, "00_WorkHstr", "BackTest_Output")
WH = os.path.join(ROOT, "00_WorkHstr")
INDEX = os.path.join(ROOT, "00_WorkHstr", "00WorkHstr_INDEX.txt")
LEVG = [3, 4, 5, 6, 8, 10, 13]
SZG = [50, 55, 65, 75, 85, 100]
TIERS = [("M0", -1e9), ("M30", -30.0), ("M25", -25.0), ("M20", -20.0)]
BLENDS = [("OFF", set()), ("W", {"W"}), ("G", {"G"}), ("W+G", {"W", "G"}),
          ("W+G+SK", {"W", "G", "SK"}), ("W+G+S2", {"W", "G", "S2"}), ("ALL", {"W", "G", "S2", "SK"})]


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


def features(T, d1m, rev_tf):
    """진입 피처(lookahead0): 저변동&OI충격(whip)·추세역행(ctr)·강OI충격(shock2)·극단쏠림(skew)."""
    et_ms = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000).astype("int64")
    mt = (d1m.index.values.astype("int64") // 1_000_000).astype("int64")
    oiz_arr = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce").values
    c = d1m["close"].values
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    tr = (dfx["high"] - dfx["low"]) / dfx["close"]
    atrp = tr.rolling(14, min_periods=5).mean().rolling(720, min_periods=120).rank(pct=True).values
    dfx_ms = (dfx.index.values.astype("int64") // 1_000_000).astype("int64")
    # 롱숏쏠림 ls_s (regime parquet, 진입봉 매핑)
    rg = pd.read_parquet(REG, columns=["timestamp", "ls_s"])
    rg["timestamp"] = pd.to_datetime(rg["timestamp"], utc=True).dt.tz_localize(None)
    rg = rg.set_index("timestamp").sort_index()
    rg_ms = (rg.index.values.astype("int64") // 1_000_000).astype("int64")
    ls_arr = rg["ls_s"].values
    lq80 = np.nanquantile(np.abs(ls_arr), 0.8)
    side = T["side"].astype(int).values
    n = len(T); oiz = np.zeros(n); apct = np.full(n, 0.5); trend = np.empty(n, dtype=object); ls = np.zeros(n)
    for i in range(n):
        j = max(0, int(np.searchsorted(mt, et_ms[i], "right")) - 1)
        oiz[i] = oiz_arr[j] if not np.isnan(oiz_arr[j]) else 0.0
        ch = (c[j] / c[max(0, j - 10080)] - 1.0) * 100.0 if j > 0 else 0.0
        trend[i] = "up" if ch > 3 else ("down" if ch < -3 else "range")
        k = max(0, int(np.searchsorted(dfx_ms, et_ms[i], "right")) - 1)
        apct[i] = atrp[k] if (k < len(atrp) and not np.isnan(atrp[k])) else 0.5
        r = max(0, int(np.searchsorted(rg_ms, et_ms[i], "right")) - 1)
        ls[i] = ls_arr[r] if not np.isnan(ls_arr[r]) else 0.0
    ctr = np.array([(trend[i] == "up" and side[i] == -1) or (trend[i] == "down" and side[i] == 1) for i in range(n)])
    return dict(whip=(apct <= 0.30) & (np.abs(oiz) >= 1.0), ctr=ctr, shock2=np.abs(oiz) >= 2.0,
                skew=np.abs(ls) >= lq80, lq80=lq80)


def blend_w(F, levers):
    w = np.ones(len(F["ctr"]))
    if "W" in levers: w[F["whip"]] *= 0.5
    if "G" in levers: w[F["ctr"]] *= 0.5
    if "S2" in levers: w[F["shock2"]] *= 0.5
    if "SK" in levers: w[F["skew"]] *= 0.5
    return w


def sized_p(Rc, MAE, FUND, lev, sz, w):
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


def metrics_on(idx, Rc, MAE, FUND, w, lev, sz, periods):
    if len(idx) == 0:
        return 0.0, 0.0, -100.0, 0
    p, nliq = sized_p(Rc[idx], MAE[idx], FUND[idx], lev, sz, w[idx])
    bal = 10000.0; peak = 10000.0; mdd = 0.0
    for x in p:
        bal *= (1.0 + x); peak = max(peak, bal); mdd = min(mdd, bal / peak - 1.0)
    nmon = (periods[idx].max() - periods[idx].min()).n + 1
    cagr = ((bal / 1e4) ** (12.0 / max(nmon, 1)) - 1.0) * 100 if bal > 0 else -100.0
    return (bal / 1e4 - 1) * 100, mdd * 100, cagr, nliq


def tier_sweep(allidx, Rc, MAE, FUND, w, periods):
    best = {k: None for k, _ in TIERS}
    for lev in LEVG:
        for sz in SZG:
            tot, mdd, _, nl = metrics_on(allidx, Rc, MAE, FUND, w, lev, sz, periods)
            for k, cap in TIERS:
                if mdd >= cap and (best[k] is None or tot > best[k]["tot"]):
                    best[k] = dict(tot=round(tot, 0), mdd=round(mdd, 1), nliq=nl, lev=lev, sz=sz)
    return best


def pick_m20(idx, Rc, MAE, FUND, w, periods):
    best = None; bm = None
    for lev in LEVG:
        for sz in SZG:
            _, mdd, cagr, _ = metrics_on(idx, Rc, MAE, FUND, w, lev, sz, periods)
            if mdd >= -20.0 and (best is None or cagr > best[2]):
                best = (lev, sz, cagr)
            if bm is None or mdd > bm[2]:
                bm = (lev, sz, mdd)
    return (best[0], best[1]) if best else (bm[0], bm[1])


def cpcv(w, Rc, MAE, FUND, periods, tblk):
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
        lev, sz = pick_m20(tri, Rc, MAE, FUND, w, periods)
        _, mdd, cagr, _ = metrics_on(tei, Rc, MAE, FUND, w, lev, sz, periods)
        cags.append(cagr); mdds.append(mdd)
    cags = np.array(cags); mdds = np.array(mdds)
    return dict(p25=np.percentile(cags, 25), neg=100 * (cags < 0).mean(),
                mdd_worst=mdds.min(), mdd_viol=100 * (mdds < -20).mean(), n=len(cags))


def main():
    _p(f"[{BASE}] 레버 배합(휩소+진입품질) — §26 4단 천장(가능성) + OOS CPCV(보조)")
    p = json.load(open(WINNERS, encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    T = make_ledger(p, 0.7, 1.0, False, d1m, fund)
    Rc = cost_real(T); MAE = T["mae"].values.astype(float); FUND = T["fund"].values.astype(float)
    periods = pd.PeriodIndex(pd.to_datetime(T["et"]).dt.to_period("M"))
    F = features(T, d1m, int(p["rev_tf"]))
    allidx = np.arange(len(T))
    _p(f"  베이스 R+P70 {len(T)}거래 · 레버대상: 휩소 {F['whip'].mean()*100:.0f}% · 추세역행 {F['ctr'].mean()*100:.0f}% · 강OI충격 {F['shock2'].mean()*100:.0f}% · 극단쏠림 {F['skew'].mean()*100:.0f}%")
    t0, m0, _, _ = metrics_on(allidx, Rc, MAE, FUND, np.ones(len(T)), 6, 55, periods)
    _p(f"  [무손상] OFF lev6/55 = {t0:+.0f}%/MDD{m0:.0f}% (Stg1 +8669%/-21% 기대)")
    if abs(t0 - 8669) > 200:
        _p("  ❌ 무손상 경고 — 중단."); return False

    cal = pd.period_range(periods.min(), periods.max(), freq="M")
    blocks = np.array_split(np.arange(len(cal)), 6); m2b = {}
    for bi, blk in enumerate(blocks):
        for mi in blk:
            m2b[cal[mi]] = bi
    tblk = np.array([m2b[per] for per in periods])

    rows = []
    for nm, lev_set in BLENDS:
        w = blend_w(F, lev_set)
        ts = tier_sweep(allidx, Rc, MAE, FUND, w, periods)
        cv = cpcv(w, Rc, MAE, FUND, periods, tblk)
        rows.append((nm, ts, cv, int((w < 1).sum())))
        _p(f"  배합 {nm:<8} 완료 (영향거래 {int((w<1).sum())})")

    # ── 보고 (§26 4단 천장 먼저=가능성, CPCV 보조) ──
    L = []
    L.append(f"[레버 배합 — §26 4단 천장 + OOS CPCV] {BASE}")
    L.append("[지침] MDD-20은 인증 게이트일 뿐 — 4단 천장(M0/M30/M25/M20 최대수익)을 먼저 본다(§26·캡틴: 가능성 싹 자르지 말 것).")
    L.append("[레버] W=저변동&OI충격 · G=추세역행 · S2=강OI충격(|z|≥2) · SK=극단쏠림. 전부 size×0.5·lookahead0.")
    L.append("")
    L.append("[★§26 4단 in-sample 최대수익 (수익률% — 가능성 천장)]")
    L.append(f"{'배합':<10}{'M0(무제한)':>16}{'M30(≥-30)':>14}{'M25(≥-25)':>14}{'M20(≥-20)':>14}")
    for nm, ts, cv, nimp in rows:
        def c(k):
            v = ts[k]
            return f"{v['tot']:+.0f}%({v['mdd']:.0f})" if v else "-"
        L.append(f"{nm:<10}{c('M0'):>16}{c('M30'):>14}{c('M25'):>14}{c('M20'):>14}")
    L.append("")
    L.append("[★OOS CPCV 표준6 (보조 — 정직 리스크)]")
    L.append(f"{'배합':<10}{'p25(연%)':>10}{'음수폴드%':>10}{'최악폴드MDD':>12}{'MDD-20위반%':>12}{'M20천장수익':>12}")
    off_viol = rows[0][2]["mdd_viol"]
    for nm, ts, cv, nimp in rows:
        m20t = f"{ts['M20']['tot']:+.0f}%" if ts['M20'] else "-"
        L.append(f"{nm:<10}{cv['p25']:>+9.0f}%{cv['neg']:>9.0f}%{cv['mdd_worst']:>+11.0f}%{cv['mdd_viol']:>11.0f}%{m20t:>12}")
    L.append("")
    # 최선 배합(위반 최소·p25 양수 중 M20천장 최대)
    cands = [(nm, ts, cv) for nm, ts, cv, _ in rows if cv["p25"] > 0]
    by_viol = sorted(cands, key=lambda x: (x[2]["mdd_viol"], -(x[1]["M20"]["tot"] if x[1]["M20"] else 0)))
    L.append("[판정]")
    if by_viol:
        bn, bts, bcv = by_viol[0]
        L.append(f"  · ★OOS MDD-20위반 최소 배합 = {bn}: 위반 {bcv['mdd_viol']:.0f}%(OFF {off_viol:.0f}%) · p25 {bcv['p25']:+.0f}% · M20천장 {bts['M20']['tot'] if bts['M20'] else '-'}%")
        L.append(f"  · 위반 0% 달성: {'★예 — '+bn+' 챔피언 인증(M20) 후보' if bcv['mdd_viol']==0 else '아직(최소 '+str(round(bcv['mdd_viol']))+'%) — 배합으로 줄지만 0은 미달, 알파레버 추가 여지(캡틴: 휩소는 하나일뿐)'}")
    L.append("  · ★4단 천장(M0/M30/M25)은 배합으로도 거대(가능성 살아있음) — MDD-20 미달=가능성 차단 아님(§26 탐색단계).")
    L.append("  · ★경계: in-sample 4단=과적합 상한. CPCV가 정직 리스크. 채택=인증(M20 위반0)+§9 별도.")
    body = "\n".join(L)

    folder = os.path.join(OUTDIR, BASE); os.makedirs(folder, exist_ok=True)
    csv = []
    for nm, ts, cv, nimp in rows:
        d = dict(배합=nm, 영향거래=nimp, CPCV_p25=round(cv["p25"], 0), CPCV_음수폴드=round(cv["neg"], 0),
                 CPCV_최악MDD=round(cv["mdd_worst"], 1), CPCV_MDD20위반=round(cv["mdd_viol"], 0))
        for k, _ in TIERS:
            v = ts[k]
            d[f"{k}_수익"] = v["tot"] if v else None
            d[f"{k}_MDD"] = v["mdd"] if v else None
        csv.append(d)
    pd.DataFrame(csv).to_csv(os.path.join(folder, f"{BASE}_배합표.csv"), index=False, encoding="utf-8-sig")
    open(os.path.join(folder, f"{BASE}_분석.txt"), "w", encoding="utf-8").write(body)
    ts2 = datetime.now().strftime("%Y%m%d%H%M")
    open(os.path.join(WH, f"{ts2}_{BASE}.txt"), "w", encoding="utf-8").write(body)
    bn = by_viol[0][0] if by_viol else "-"; bv = by_viol[0][2]["mdd_viol"] if by_viol else -1
    with open(INDEX, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{BASE}|레버배합 휩소+진입품질 §26 4단+OOS CPCV: "
                f"위반최소 {bn} {bv:.0f}%(OFF {off_viol:.0f}%)·4단천장 거대(가능성 유지)|src={BASE}.py\n")
    _p("\n" + body)
    _p(f"\n[저장] {folder}\\  · 배합표.csv · 분석.txt")
    return True


if __name__ == "__main__":
    main()
