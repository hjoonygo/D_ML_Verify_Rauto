# -*- coding: utf-8 -*-
# [portfolio_cpcv_oos.py] (A) 실전 진입 규칙화 1단계 — TS20/REV80 @노출1.2 포트폴리오의 OOS/CPCV 견고성 검증.
#   목적: port_lev.py의 +137%/MDD-20.0%는 가중치(20/80)·노출(1.2)을 *full표본*에서 골라 MDD가 -20 경계에 딱 붙음(칼날 의심).
#         §5.6·§15.5 = "채택은 CPCV 표준6 통과만". 이 손잡이들이 OOS서 살아남는지(고원/칼날) 검증한 뒤에만 규칙 박제.
#   방법(§15.1 검증엔진 재사용·재구현 금지):
#     - TS 스트림 = trendstack_signal_engine.run_strategy (port_lev와 동일 설정) → exit_seq(1m 실체결·갭·비용8bp)
#     - REV 스트림 = vol_sizing_compare.build (mom_24h+oi_z reversion) → 동일 exit_seq
#     - 두 스트림을 '월복리 수익률'로 집계·캐시(streams_monthly.csv). 이후 분석은 캐시로 빠르게.
#   검증 3종:
#     (1) 2D 견고성 격자: 가중치 w_rev × 노출 exp 에서 MDD>-20 가능영역이 고원인지 점인지.
#     (2) ★CPCV 표준6(15경로): 각 test조합에서 가중치·노출을 train월로 재선택→test월 평가(선택절차 자체 OOS).
#         + 고정config(w_rev0.8/exp1.2) OOS 동시 평가(특정 config 일반화 여부).
#     (3) 연도별 분해(매년 양수?).
#   판정 = CPCV p25(test CAGR)>0 AND test MDD 위반비율 낮음 AND 매년 양수 → '채택' 후보. 미달=어느 손잡이 overfit 보고.
import sys, os, itertools
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\verification")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
import vol_sizing_compare as V

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\RfRauto\08_BTC_Data\derived\Merged_Data.csv"
CACHE = os.path.join(HERE, "streams_monthly.csv")
COST = 0.0008; SL_MULT = 1.5; TRAIL = 0.03; TF = TS.TF_MIN
# full표본 채택값(앵커) — port_lev.py 와 동일
W_REV_FULL = 0.8; EXP_FULL = 1.2
EMBARGO_M = 1   # CPCV test 그룹 인접 train월 엠바고(월내 거래의 월경계 누수 차단)


def _p(*a): print(*a, flush=True)


def exit_seq(d, ents):
    """port_lev.py 와 1:1 동일 — 1m 실체결·갭반영·트레일·사이징(sat×soi)·비용8bp."""
    ti = d.index; O = d["open"].values; H = d["high"].values; L = d["low"].values; C = d["close"].values
    aps = [e["atr_pct"] for e in ents]; med = np.median(aps) if aps else 0.02
    ents = sorted(ents, key=lambda e: e["et_fill"]); rows = []; last_xt = None
    for e in ents:
        if last_xt is not None and e["et_fill"] < last_xt: continue
        side = e["side"]; entry = e["entry"]; ap = e["atr_pct"]; oi = e["oi_z"]
        risk = float(np.clip(ap * SL_MULT, 0.008, 0.05)); si = ti.searchsorted(e["et_fill"])
        if si >= len(ti): continue
        TSL = entry * (1 - risk) if side == 1 else entry * (1 + risk); hwm = H[si]; lwm = L[si]; ex = None; xi = len(ti) - 1
        for i in range(si, len(ti)):
            if side == 1 and L[i] <= TSL: ex = min(O[i], TSL); xi = i; break
            if side == -1 and H[i] >= TSL: ex = max(O[i], TSL); xi = i; break
            if H[i] > hwm: hwm = H[i]
            if L[i] < lwm: lwm = L[i]
            TSL = max(TSL, hwm * (1 - TRAIL)) if side == 1 else min(TSL, lwm * (1 + TRAIL))
        if ex is None: ex = C[-1]
        ret = side * (ex - entry) / entry - COST
        soi = np.clip(1 - 0.3 * max(0, oi - 1.5), 0.25, 1); sat = np.clip(med / ap, 0.25, 1)
        rows.append(dict(et=e["et"], ret=ret * sat * soi)); last_xt = ti[xi]
    return pd.DataFrame(rows)


def gen_streams():
    """TS·REV 거래 생성 → 월복리 수익률 2스트림. 캐시 있으면 로드."""
    if os.path.exists(CACHE):
        m = pd.read_csv(CACHE); _p(f"[캐시] {CACHE} ({len(m)}개월)")
        return m["month"].values, m["ts"].values, m["rev"].values
    _p("[생성] 1m 실체결 스트림 생성 중(느림)…")
    d = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low", "close", "oi_zscore_24h"])
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    d = d.dropna(subset=["open", "high", "low", "close"]).set_index("t").sort_index()
    doi = pd.to_numeric(d["oi_zscore_24h"], errors="coerce")
    # TS 스트림
    df7h = TS.resample_tf(d[["open", "high", "low", "close"]], TF); sig = TS.compute_signals(df7h)
    tstr = TS.run_strategy(df7h, sig, 0, "none", 0.8, gate_mode="er", gate_er=0.45, split_mode="A", split_n=3, fib=(0.3, 0.5, 0.6))
    atrp = sig["atr"] / df7h["close"].values; er = sig["er"]; oi7 = doi.reindex(df7h.index, method="ffill").values; idx7 = df7h.index
    ts_e = []
    for tr in tstr:
        ei = idx7.get_loc(tr["entry_t"])
        if er[ei] < 0.40: continue
        ts_e.append(dict(et=pd.Timestamp(tr["entry_t"]), et_fill=pd.Timestamp(tr["entry_t"]) + pd.Timedelta(minutes=TF),
            side=int(tr["side"]), entry=float(tr["entry"]), atr_pct=float(atrp[ei]) if atrp[ei] > 0 else 0.02,
            oi_z=float(oi7[ei]) if not np.isnan(oi7[ei]) else 0.0))
    TSL_ = exit_seq(d, ts_e)
    # REV 스트림
    d2, S, oi_int = V.build(V.find_data()); oimap = dict(zip(list(S.index), list(oi_int)))
    rev_e = []
    for t, row in S.iterrows():
        if row["side"] == 0: continue
        tn = t.tz_localize(None) if t.tz is not None else t
        rev_e.append(dict(et=tn, et_fill=tn, side=int(row["side"]), entry=float(row["open8"]),
            atr_pct=float(row["atr_pct"]), oi_z=float(oimap.get(t, 0.0))))
    REV = exit_seq(d, rev_e)
    TSL_["m"] = TSL_.et.dt.to_period("M"); REV["m"] = REV.et.dt.to_period("M")
    tsm = TSL_.groupby("m").ret.apply(lambda x: ((1 + x).prod() - 1)); revm = REV.groupby("m").ret.apply(lambda x: ((1 + x).prod() - 1))
    allm = sorted(set(tsm.index) | set(revm.index))
    ts_s = tsm.reindex(allm, fill_value=0.0).values; rev_s = revm.reindex(allm, fill_value=0.0).values
    months = [str(x) for x in allm]
    pd.DataFrame({"month": months, "ts": ts_s, "rev": rev_s}).to_csv(CACHE, index=False, encoding="utf-8-sig")
    _p(f"[생성완료] {len(months)}개월 → 캐시 저장. TS거래 {len(TSL_)} REV거래 {len(REV)}")
    return np.array(months), ts_s, rev_s


def stats(m):
    """월수익률 배열 → (총수익%, MDD%, CAGR%/yr)."""
    if len(m) == 0: return 0.0, 0.0, 0.0
    eq = np.cumprod(1 + m); tot = (eq[-1] - 1) * 100
    mdd = ((eq - np.maximum.accumulate(eq)) / np.maximum.accumulate(eq)).min() * 100
    cagr = ((1 + tot / 100) ** (12 / len(m)) - 1) * 100   # 월수 기반 연율화
    return tot, mdd, cagr


def select_best(ts, rev, ws, es):
    """train 월에서 MDD>-20 안 최대수익 (w_rev, exp) 선택 = full표본 절차 복제."""
    best = None
    for w in ws:
        port = (1 - w) * ts + w * rev
        for e in es:
            tot, mdd, _ = stats(port * e)
            if mdd > -20 and (best is None or tot > best[0]):
                best = (tot, w, e)
    if best is None:   # MDD>-20 불가능하면 최소노출
        return ws[len(ws) // 2], es[0]
    return best[1], best[2]


def main():
    months, ts_s, rev_s = gen_streams()
    n = len(months)
    yrs = np.array([int(x[:4]) for x in months])
    corr = np.corrcoef(ts_s, rev_s)[0, 1]
    _p(f"\n[스트림] {n}개월 ({months[0]}~{months[-1]}) | 월상관 {corr:+.2f}")
    tt, tm, tc = stats(ts_s); rt, rm, rc = stats(rev_s)
    _p(f"  TS only  : tot {tt:+.0f}%  MDD {tm:.1f}%  CAGR {tc:.1f}%/yr")
    _p(f"  REV only : tot {rt:+.0f}%  MDD {rm:.1f}%  CAGR {rc:.1f}%/yr")

    # ── (0) 앵커 재현 ──
    pf = (1 - W_REV_FULL) * ts_s + W_REV_FULL * rev_s
    at, am, ac = stats(pf * EXP_FULL)
    _p(f"\n[앵커] full표본 TS20/REV80 @노출{EXP_FULL}: tot {at:+.0f}%  MDD {am:.1f}%  CAGR {ac:.1f}%/yr  월양수 {100*(pf*EXP_FULL>0).mean():.0f}%")
    _p(f"       (port_lev.py 기대값 +137%/-20.0%/33.4% 와 대조)")

    # ── (1) 2D 견고성 격자 ──
    ws = np.round(np.arange(0.0, 1.001, 0.1), 2); es = np.round(np.arange(0.5, 3.001, 0.1), 2)
    _p(f"\n[견고성] 가중치 w_rev × 노출 exp 격자 — 각 칸 = MDD>-20면 총수익%, 아니면 '·'")
    _p("w_rev\\exp " + "".join(f"{e:>6.1f}" for e in [0.5, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]))
    for w in ws:
        port = (1 - w) * ts_s + w * rev_s; cells = []
        for e in [0.5, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
            tot, mdd, _ = stats(port * e)
            cells.append(f"{tot:>6.0f}" if mdd > -20 else f"{'·':>6}")
        _p(f"  {w:>5.1f}   " + "".join(cells))
    # 전역 최적(full표본)
    bw, be = select_best(ts_s, rev_s, ws, es)
    bt, bm, bc = stats(((1 - bw) * ts_s + bw * rev_s) * be)
    _p(f"  → full표본 전역최적: w_rev {bw:.1f} / exp {be:.1f} → tot {bt:+.0f}% MDD {bm:.1f}% CAGR {bc:.1f}%/yr")

    # ── (2) CPCV 표준6 (15경로) ──
    g6 = np.array_split(np.arange(n), 6)
    _p(f"\n[CPCV 표준6] 6그룹×2 test = 15경로. 폴드마다 train월서 (w_rev,exp) 재선택→test월 평가(선택절차 OOS).")
    _p(f"{'test그룹':<10}{'sel_w':>6}{'sel_e':>6}{'train수익%':>10}{'trainMDD':>9}{'TESTcagr%':>10}{'TESTmdd%':>9}")
    _p("-" * 70)
    sel_cagr = []; sel_mdd = []; fix_cagr = []; fix_mdd = []
    for c in itertools.combinations(range(6), 2):
        test_idx = np.sort(np.concatenate([g6[k] for k in c]))
        emb = set()
        for k in c:
            lo, hi = g6[k][0], g6[k][-1]
            for j in range(1, EMBARGO_M + 1):
                emb.add(lo - j); emb.add(hi + j)
        train_idx = np.array([i for i in range(n) if i not in set(test_idx) and i not in emb])
        ts_tr, rev_tr = ts_s[train_idx], rev_s[train_idx]
        ts_te, rev_te = ts_s[test_idx], rev_s[test_idx]
        # (2a) 폴드 재선택
        w, e = select_best(ts_tr, rev_tr, ws, es)
        trt, trm, _ = stats(((1 - w) * ts_tr + w * rev_tr) * e)
        port_te = ((1 - w) * ts_te + w * rev_te) * e
        tet, tem, tec = stats(port_te)
        sel_cagr.append(tec); sel_mdd.append(tem)
        # (2b) 고정 config OOS
        fp = ((1 - W_REV_FULL) * ts_te + W_REV_FULL * rev_te) * EXP_FULL
        _, fm, fc = stats(fp); fix_cagr.append(fc); fix_mdd.append(fm)
        _p(f"{str(c):<10}{w:>6.1f}{e:>6.1f}{trt:>+10.0f}{trm:>+9.1f}{tec:>+10.1f}{tem:>+9.1f}")
    sel_cagr = np.array(sel_cagr); sel_mdd = np.array(sel_mdd); fix_cagr = np.array(fix_cagr); fix_mdd = np.array(fix_mdd)
    _p("-" * 70)
    _p(f"[2a 선택절차 OOS] test CAGR: p25 {np.percentile(sel_cagr,25):+.1f}%  중앙 {np.median(sel_cagr):+.1f}%  최악 {sel_cagr.min():+.1f}%  음수 {100*(sel_cagr<0).mean():.0f}%")
    _p(f"                 test MDD : 중앙 {np.median(sel_mdd):.1f}%  최악 {sel_mdd.min():.1f}%  -20위반 {100*(sel_mdd<-20).mean():.0f}%")
    _p(f"[2b 고정 20/80@1.2 OOS] test CAGR: p25 {np.percentile(fix_cagr,25):+.1f}%  중앙 {np.median(fix_cagr):+.1f}%  최악 {fix_cagr.min():+.1f}%  음수 {100*(fix_cagr<0).mean():.0f}%")
    _p(f"                       test MDD : 중앙 {np.median(fix_mdd):.1f}%  최악 {fix_mdd.min():.1f}%  -20위반 {100*(fix_mdd<-20).mean():.0f}%")

    # ── (3) 연도별 분해 (고정 config) ──
    _p(f"\n[연도별] 고정 TS20/REV80 @노출{EXP_FULL} (매년 양수?)")
    _p(f"{'연도':<8}{'개월':>5}{'수익%':>9}{'MDD%':>8}")
    full = pf * EXP_FULL
    for y in sorted(set(yrs)):
        sel = yrs == y; t, m, _ = stats(full[sel])
        _p(f"{y:<8}{int(sel.sum()):>5}{t:>+9.1f}{m:>+8.1f}")

    _p(f"\n[판정 기준] §15.5 채택 = (2)CPCV p25>0 AND test MDD -20위반 낮음 AND (3)매년 양수.")
    _p(f"[정직] 36개월 월수익(스트림) = CPCV 표본 얇음. 거래레벨 아닌 월복리 단위. 노출=레버리지 대용(자본대비 명목).")


if __name__ == "__main__":
    main()
