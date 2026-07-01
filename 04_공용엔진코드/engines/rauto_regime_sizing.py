# -*- coding: utf-8 -*-
# [rauto_regime_sizing.py] ★레짐적응 사이징 — 봇무관 PlugIn (Rauto 결정두뇌 도메인·§25) (세션 260702_01_MicroRegimeWhip).
#   목적: 진입 미세레짐에 따라 '노출(사이징)'을 배수 조정. 사이징=Rauto 중앙 소관(봇 알파 불변) = §25 경계.
#   ★L2 랠리억제(260702_01 진단·검증): 상승추세(7일추세≥thr)서 REVoi '역주행'(추세반대 side) 진입의 노출을 factor배 축소.
#     근거 = Stg1 진단(랠리 역주행=최대 저EV 손실기여 39%) → Stg2 held-out OOS 수익 2배(+1058→+2155%) → Stg3 정밀화.
#     비대칭(급락롱=REVoi 강점, 절대 안 건드림) · ×0.3~0.5(skip는 레버업 함정) · 임계 7일추세 +3%.
#   ★구조: 봇무관(원장 et·side + 중앙 d1m만) · causal(7일추세=진입 직전 완성 4H봉 shift1·lookahead0·라이브 계산가능).
#   ★무손상: 원장에 'size_mult' 컬럼을 붙일 뿐 — 이 컬럼을 읽는 엔진(veri_edge._liq·rauto_live.per_trade_pnl)만
#     반영하고, 컬럼 없으면 기존과 100% 동일(하위호환). off(전부 1.0)면 앵커 무변.
#   ★emergency_brake.py(안전장치1호)와 동일 패턴 = 봇무관 사이징 PlugIn. LogicCatalog D8 예약.
import numpy as np
import pandas as pd
import trendstack_signal_engine as TS

W4 = 42                       # 7일 = 42개 4H봉(라이브 챔피언 7일추세 분류기와 동일)
RALLY_THR = 3.0               # 상승추세 임계(%): 7일변화 ≥ +3% = 랠리
RALLY_FACTOR = 0.5            # 랠리 역주행 노출 배수(0.3~0.5; skip=0은 레버업 함정=금지, Stg3)


def trend7_series(d1m, rev_tf):
    """진입 직전 완성 4H봉까지의 7일추세(%) 시리즈 + 그 4H봉 시작ms. causal(shift1·lookahead0)."""
    dfx = TS.resample_tf(d1m[["open", "high", "low", "close"]], rev_tf)
    c4 = dfx["close"]
    tr = ((c4 / c4.shift(W4) - 1.0) * 100.0).shift(1).values         # ★shift1 = 직전 완성봉 = lookahead0
    dfx_ms = (dfx.index.values.astype("int64") // 1_000_000)
    return tr, dfx_ms


def rally_damp_mult(trend7, side, thr=RALLY_THR, factor=RALLY_FACTOR):
    """단건: 상승추세(≥thr)서 역주행(숏=side −1) → factor배, 그 외 1.0. (급락롱은 비대칭=안 건드림)"""
    if trend7 is None or np.isnan(trend7):
        return 1.0
    return float(factor) if (trend7 >= thr and side == -1) else 1.0


def size_mult_for_ledger(T, d1m, rev_tf, thr=RALLY_THR, factor=RALLY_FACTOR):
    """배치: 원장 T(et,side) → per-trade 노출 배수 np배열. 봇무관·causal."""
    et_ms = (pd.to_datetime(T["et"]).values.astype("int64") // 1_000_000)
    side = T["side"].astype(int).values
    tr, dfx_ms = trend7_series(d1m, rev_tf)
    n = len(T); mult = np.ones(n)
    for i in range(n):
        k = max(0, int(np.searchsorted(dfx_ms, et_ms[i], "right")) - 1)
        t7 = tr[k] if k < len(tr) else np.nan
        mult[i] = rally_damp_mult(t7, side[i], thr, factor)
    return mult


def apply_rally_damp(T, d1m, rev_tf, thr=RALLY_THR, factor=RALLY_FACTOR):
    """원장 T에 'size_mult' 컬럼을 붙여 반환(사본). 이 컬럼을 읽는 엔진만 반영(하위호환·무손상)."""
    T = T.copy()
    T["size_mult"] = size_mult_for_ledger(T, d1m, rev_tf, thr, factor)
    return T


# ── 자가검증(봇무관·causal·무손상 논리) ──
if __name__ == "__main__":
    import os, sys, json
    ROOT = r"D:\ML\RfRauto"
    sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
    sys.path.insert(0, os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp"))
    from path_finder import ensure_paths; ensure_paths()
    from fib_replay_1m import load_1m, load_funding
    from REVoi_bot import REVoiBot

    def _p(*a): print(*a, flush=True)
    _p("[rauto_regime_sizing 자가검증]")
    # 단건 논리
    assert rally_damp_mult(5.0, -1) == 0.5, "랠리 숏 → 0.5"
    assert rally_damp_mult(5.0, 1) == 1.0, "랠리 롱(안건드림) → 1.0"
    assert rally_damp_mult(-5.0, -1) == 1.0, "하락 숏 → 1.0"
    assert rally_damp_mult(0.0, -1) == 1.0, "횡보 → 1.0"
    assert rally_damp_mult(np.nan, -1) == 1.0, "워밍업 부족 → 1.0(안전)"
    assert rally_damp_mult(5.0, -1, factor=0.3) == 0.3, "강도 0.3"
    _p("  ① 단건 damp 논리 5종 PASS (비대칭·NaN안전·강도)")
    # 배치(실원장) — causal·범위·비율
    p = json.load(open(os.path.join(ROOT, r"03_IDEA4Bot\260623_07_RfRautoAlphaUp\back2tv_rev_winners.json"), encoding="utf-8"))["REV_MDD25_36mo"]["p"]
    combo = {**p, "tp_frac": 0.7, "early_tp_pct": 0.01, "early_frac": 1.0}
    d1m, fund = load_1m(), load_funding()
    T = REVoiBot(combo).make_trades(d1m, fund).sort_values("et").reset_index(drop=True)
    T2 = apply_rally_damp(T, d1m, int(p["rev_tf"]))
    m = T2["size_mult"].values
    nd = int((m < 1.0).sum())
    # damp된 건 전부 숏이어야(비대칭 보장)
    damped_all_short = bool((T2.loc[m < 1.0, "side"].astype(int) == -1).all())
    _p(f"  ② 실원장 {len(T2)}거래 · damp {nd}건({100*nd/len(T2):.0f}%) · damp된것 전부숏={damped_all_short} · 배수 유일값={sorted(set(np.round(m,3)))}")
    assert damped_all_short, "damp는 랠리 숏만(비대칭)"
    assert set(np.round(m, 3)) <= {0.5, 1.0}, "배수 ∈ {0.5,1.0}"
    # off(임계 크게) → 전부 1.0 = 무손상
    T3 = apply_rally_damp(T, d1m, int(p["rev_tf"]), thr=1e9)
    assert (T3["size_mult"].values == 1.0).all(), "off → 전부1.0(무손상)"
    _p("  ③ off(thr=∞) → size_mult 전부 1.0 = 무손상 보장 PASS")
    _p("  ✅ 자가검증 통과 — 봇무관·causal·비대칭·무손상")
