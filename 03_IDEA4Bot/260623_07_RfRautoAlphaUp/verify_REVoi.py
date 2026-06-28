# -*- coding: utf-8 -*-
# [verify_rev3.py] #3(REV_MDD25_36mo) 환각·미래참조 철저검증 (캡틴 지시 2026-06-24).
#   A. oi_zscore 룩어헤드: ① 워밍업 NaN(롤링지표인가) ② 롤링z 아핀불변 증명(full표본 정규화 무해화).
#   B. 1m 겹침 실측: 932거래 전부 진입체결·청산체결이 '실제 1m봉 범위 안'인지(가격이 그 캔들 지났나) 검사.
#      환각 시그니처 = 1m이 절대 못 닿는 가격에 체결됐다고 우기는 거래.
import os, sys, json
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
import numpy as np, pandas as pd
import trendstack_signal_engine as TS
from fib_replay_1m import load_1m, load_funding
import back2tv_REVoi as BR
HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a): print(*a, flush=True)
def rollz(s, w): return (s - s.rolling(w).mean()) / (s.rolling(w).std() + 1e-9)


def main():
    p = json.load(open(os.path.join(HERE, "back2tv_rev_winners.json")))["REV_MDD25_36mo"]["p"]
    d1m = load_1m(); fund = load_funding()
    rtf, qwin = p["rev_tf"], p["qwin"]

    _p("="*64); _p("[A. oi_zscore 룩어헤드 검증]")
    oi = pd.to_numeric(d1m["oi_zscore_24h"], errors="coerce")
    _p(f"  원본 oi_zscore_24h: 행{len(oi)} · 선두NaN {int(oi.isna()[:2000].sum())}개 · 전체 평균{oi.mean():.3f}/표준편차{oi.std():.3f}")
    df = TS.resample_tf(d1m[["open", "high", "low", "close"]], rtf)
    oir = oi.resample(f"{rtf}min", label="left", closed="left").last().reindex(df.index).shift(1)
    za = rollz(oir, qwin); zb = rollz(5.0 * oir + 100.0, qwin)   # 아핀변환
    diff = float(np.nanmax(np.abs((za - zb).values)))
    _p(f"  ★롤링z 아핀불변: rollz(oi) vs rollz(5*oi+100) 최대차 {diff:.2e}")
    _p(f"    → {'동일(≈0) = 롤링z가 full표본 정규화를 상쇄 → oi_zscore가 설령 전표본z여도 룩어헤드 무해' if diff < 1e-6 else '差존재=조사필요'}")
    _p(f"  ★시점: mom=open(봉시작 확정)·oi=shift(1)(직전봉)·롤링z/롤링분위=과거 {qwin}봉만 → 신호[i]는 봉 i 시작에 확정")

    _p("\n[B. 1m 겹침 실측 — #3의 932거래]")
    T = BR.rev_trades(d1m, fund, p, capture_fills=True).sort_values("et").reset_index(drop=True)
    m_t = d1m.index.values; mO = d1m["open"].values; mH = d1m["high"].values; mL = d1m["low"].values
    tf_td = np.timedelta64(rtf, "m")

    def bar1m(t):
        k = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(t)), "left"))
        return k if 0 <= k < len(m_t) else -1

    ent_ok = ent_bad = 0; ex_ok = ex_bad = 0; ex_reach_bad = 0; bad_list = []
    TOL = 0.6  # $ 허용오차(틱·반올림)
    for r in T.itertuples():
        side = int(r.side)
        # 진입 체결점들: 각 fill 가격이 그 1m봉 [저,고] 안인가
        for ft, fp in (r.fills if isinstance(r.fills, list) else []):
            k = bar1m(ft)
            if k < 0: continue
            if mL[k] - TOL <= fp <= mH[k] + TOL: ent_ok += 1
            else:
                ent_bad += 1
                if len(bad_list) < 6: bad_list.append(f"진입 {pd.Timestamp(ft)} fp{fp:.1f} not in [{mL[k]:.1f},{mH[k]:.1f}]")
        # 청산 체결: xt_fill 1m봉 범위 + 보유창서 실제 도달했나
        xk = bar1m(getattr(r, "xt_fill", r.xt))
        if xk >= 0:
            if mL[xk] - TOL <= r.exit <= mH[xk] + TOL: ex_ok += 1
            else:
                ex_bad += 1
                if len(bad_list) < 12: bad_list.append(f"청산 {pd.Timestamp(getattr(r,'xt_fill',r.xt))} px{r.exit:.1f} not in [{mL[xk]:.1f},{mH[xk]:.1f}] ({r.reason})")
        # 보유창 [진입봉, 청산봉+tf] 내 1m이 청산가에 실제 닿았나(롱=저<=exit / 숏=고>=exit)
        a = bar1m(r.et); b = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(r.xt)) + tf_td, "left"))
        if 0 <= a < b <= len(m_t):
            reached = (mL[a:b].min() <= r.exit + TOL) if side == 1 else (mH[a:b].max() >= r.exit - TOL)
            if not reached: ex_reach_bad += 1
    nf = sum(len(r.fills) for r in T.itertuples() if isinstance(r.fills, list))
    _p(f"  거래 {len(T)} · 진입 체결점 {nf}개")
    _p(f"  ① 진입체결 1m범위內: {ent_ok}/{ent_ok+ent_bad} ({100*ent_ok/max(1,ent_ok+ent_bad):.1f}%) · 벗어남 {ent_bad}")
    _p(f"  ② 청산체결 1m범위內: {ex_ok}/{ex_ok+ex_bad} ({100*ex_ok/max(1,ex_ok+ex_bad):.1f}%) · 벗어남 {ex_bad}")
    _p(f"  ③ 청산가 보유창서 실제도달(환상아님): 미도달 {ex_reach_bad}건")
    if bad_list:
        _p("  [이상징후 표본]"); [_p("   - " + x) for x in bad_list]
    verdict = (ent_bad == 0 and ex_bad == 0 and ex_reach_bad == 0)
    _p("\n" + "="*64)
    _p(f"[판정] {'✅ 환각·미래참조 없음 — 전 체결이 1m봉에 실제 겹침. Back2TV 생성 진행 가능' if verdict else '❌ 이상 발견 — 위 표본 확인 필요(Back2TV 보류)'}")
    return verdict


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
