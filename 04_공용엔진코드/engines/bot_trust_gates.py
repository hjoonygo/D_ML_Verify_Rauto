# -*- coding: utf-8 -*-
# [bot_trust_gates.py] ★봇 신뢰 4관문 자동검증 레일 (세션 260625_01_RautoSysReform2).
#   목적 = '어떤 봇이든'(계약 make_trades만 맞으면) 끼워서 ①앵커 ②환각 ③CPCV ④현실비용을 자동으로 걸고
#          "이 봇 = 진짜(4관문 통과)/미검증" 한 장 판정. = 캡틴 "암만 봇 만들어도 정확한 수익·알파 자동확인"의 실현 레일.
#   ★봇 무관(보편): ②1m 겹침·③CPCV·④비용은 '원장 컬럼'만 맞으면 어떤 봇이든 동일하게 걸린다.
#   ★검증엔진 무수정·호출/분석만(§15.1): 봇 원장=검증된 make_trades 호출, CPCV/1m겹침=통계·대조(봇 로직 재구현 아님).
#   ★정직한 한계: ①앵커는 '기준값' 있어야 비교(없으면 재현성만). ②'피처 룩어헤드'(지표가 미래 보나)는 봇별 1회 점검(여긴 1m 겹침=보편).
import itertools
from path_finder import ensure_paths
ensure_paths()
import numpy as np
import pandas as pd
from rauto_cex import RautoCEX, SlipModel


def _verify_1m_overlap(T, d1m, sig_tf, tol=0.6):
    """②환각검증(보편): 모든 진입/청산 체결가가 그 1m봉 [저,고] 안 + 청산가가 보유창서 실제 도달했나.
       = verify_REVoi 'B.1m 겹침'을 봇 무관으로 추출. 반환 (ent_ok,ent_bad,ex_ok,ex_bad,reach_bad, 표본)."""
    m_t = d1m.index.values
    mH = d1m["high"].values
    mL = d1m["low"].values
    tf_td = np.timedelta64(int(sig_tf), "m")

    def bar1m(t):
        k = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(t)), "left"))
        return k if 0 <= k < len(m_t) else -1

    ent_ok = ent_bad = ex_ok = ex_bad = reach_bad = 0
    bad = []
    for r in T.itertuples():
        side = int(r.side)
        # 진입 체결점들(capture_fills) — 각 fill 가격이 그 1m봉 안인가
        fills = r.fills if isinstance(getattr(r, "fills", None), list) else []
        for ft, fp in fills:
            k = bar1m(ft)
            if k < 0:
                continue
            if mL[k] - tol <= fp <= mH[k] + tol:
                ent_ok += 1
            else:
                ent_bad += 1
                if len(bad) < 6:
                    bad.append(f"진입 {pd.Timestamp(ft)} fp{fp:.1f} not in [{mL[k]:.1f},{mH[k]:.1f}]")
        # 청산 체결 — xt_fill 1m봉 범위
        xk = bar1m(getattr(r, "xt_fill", r.xt))
        if xk >= 0:
            if mL[xk] - tol <= r.exit <= mH[xk] + tol:
                ex_ok += 1
            else:
                ex_bad += 1
                if len(bad) < 12:
                    bad.append(f"청산 {pd.Timestamp(getattr(r, 'xt_fill', r.xt))} px{r.exit:.1f} not in [{mL[xk]:.1f},{mH[xk]:.1f}] ({r.reason})")
        # 청산가가 보유창 [진입봉, 청산봉+tf] 내 1m에 실제 도달했나(환상 아님)
        a = bar1m(r.et)
        b = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(r.xt)) + tf_td, "left"))
        if 0 <= a < b <= len(m_t):
            reached = (mL[a:b].min() <= r.exit + tol) if side == 1 else (mH[a:b].max() >= r.exit - tol)
            if not reached:
                reach_bad += 1
    return ent_ok, ent_bad, ex_ok, ex_bad, reach_bad, bad


def _cpcv_stats(T):
    """③CPCV 표준6(15경로): 원장 월수익 → 폴드별 연환산 → (p25, 음수폴드비율, 경로수).
       = blend_opt.cpcv_p25와 동일 로직(통계·재구현 아님). 표본<12개월이면 (None,None,0)."""
    g = T.copy()
    g["m"] = pd.to_datetime(g["et"]).dt.to_period("M")
    port = g.groupby("m")["R"].apply(lambda x: (1.0 + x).prod() - 1.0).values
    if len(port) < 12:
        return None, None, 0
    g6 = np.array_split(np.arange(len(port)), 6)
    paths = []
    for c in itertools.combinations(range(6), 2):
        te = np.sort(np.concatenate([g6[k] for k in c]))
        seg = port[te]
        eq = np.cumprod(1.0 + seg)
        tot = (eq[-1] - 1.0) * 100.0
        paths.append(((1.0 + tot / 100.0) ** (12.0 / len(seg)) - 1.0) * 100.0)
    paths = np.array(paths)
    return float(np.percentile(paths, 25)), float((paths < 0).mean()), len(paths)


def run_gates(bot, d1m, fund, size_pct, lev, sig_tf, ref_anchor=None, ref_tol=0.5, log=print):
    """봇 1개에 4관문을 걸고 판정 dict 반환. bot=계약 make_trades(d1m,fund,capture_fills) 구현체.
       ref_anchor=알려진 기준 복리%(슬립0). 없으면 ①은 '재현성'만 판정."""
    name = getattr(bot, "NAME", "?")
    log("=" * 64)
    log(f"[봇 신뢰 4관문] 봇={name} · 사이징 레버{lev}/증거금{size_pct}% · 신호TF={sig_tf}")

    # 봇 원장(체결점 포함) — 환각검증·CPCV·비용 공용
    T = bot.make_trades(d1m, fund, capture_fills=True).sort_values("et").reset_index(drop=True)
    T["_ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
    log(f"  거래 {len(T)}건 생성(capture_fills)")

    # ④ 현실비용: 슬립0(앵커) vs 현실(청산 스프레드 1bp)
    r0 = RautoCEX(size_pct, lev, slip=SlipModel(0.0, 0.0)).run(T.copy())
    rr = RautoCEX(size_pct, lev, slip=SlipModel(0.0, 1.0)).run(T.copy())

    # ① 앵커(무손상) + 재현성(두 번 돌려 동일)
    T2 = bot.make_trades(d1m, fund, capture_fills=True).sort_values("et").reset_index(drop=True)
    T2["_ym"] = pd.to_datetime(T2["et"]).dt.to_period("M").astype(str)
    r0b = RautoCEX(size_pct, lev, slip=SlipModel(0.0, 0.0)).run(T2.copy())
    repro = abs(r0["tot"] - r0b["tot"]) < 1e-9 and len(T) == len(T2)
    anchor_ok = (ref_anchor is None) or (abs(r0["tot"] - ref_anchor) < ref_tol)
    g1 = repro and anchor_ok

    # ② 환각검증(1m 겹침)
    eok, ebad, xok, xbad, rbad, samp = _verify_1m_overlap(T, d1m, sig_tf)
    g2 = (ebad == 0 and xbad == 0 and rbad == 0)

    # ③ CPCV 표준6
    p25, neg, npath = _cpcv_stats(T)
    g3 = (p25 is not None) and (p25 > 0) and (neg == 0.0)

    # ── 출력 ──
    log("")
    log("[① 앵커·재현]  " + (f"기준 {ref_anchor:+.1f}% 대비 " if ref_anchor is not None else "기준없음 ") +
        f"슬립0={r0['tot']:+.1f}% · 재현(2회동일)={repro} → {'PASS' if g1 else 'FAIL'}")
    log(f"[② 환각검증]  진입체결 1m內 {eok}/{eok+ebad}·청산 {xok}/{xok+xbad}·보유창 미도달 {rbad} → {'PASS(환각0)' if g2 else 'FAIL(환상)'}")
    if samp:
        for s in samp[:6]:
            log("     - " + s)
    log(f"[③ CPCV 표준6] p25 {p25:+.1f}%/yr · 음수폴드 {0 if neg is None else neg*100:.0f}% ({npath}경로) → {'PASS' if g3 else 'FAIL/미달'}")
    log(f"[④ 현실비용]  슬립0 {r0['tot']:+.1f}%  vs  현실(스프1bp) {rr['tot']:+.1f}%  (차이={r0['tot']-rr['tot']:.1f}%p)")

    verdict = g1 and g2 and g3
    log("")
    log("=" * 64)
    log(f"[판정] 봇={name} : " + ("✅ 진짜(4관문 통과)" if verdict else "❌ 미검증") +
        f"  [①앵커 {'O' if g1 else 'X'} ②환각 {'O' if g2 else 'X'} ③CPCV {'O' if g3 else 'X'} ④비용 표기O]")
    log("  ※ 한계: ①은 기준값 있을 때만 진짜앵커(없으면 재현성). ②'피처 룩어헤드'는 봇별 1회 점검(여긴 1m겹침=보편). ③고정config(held-out 재최적은 별도).")
    return dict(bot=name, verdict=verdict, g1=g1, g2=g2, g3=g3,
                tot0=r0["tot"], tot_real=rr["tot"], mdd=r0["mdd"],
                cpcv_p25=p25, neg_fold=neg, ent_bad=ebad, ex_bad=xbad, reach_bad=rbad, repro=repro, n=len(T))
