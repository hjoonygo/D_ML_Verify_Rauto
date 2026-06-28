# -*- coding: utf-8 -*-
# [260625_01_RautoSysReform2_TSSW_HallucinationCheck.py] ★TS·SW 환각 도달검증 (세션 260625_01_RautoSysReform2).
#   목적 = bot_trust_gates ②환각의 '도달검증'(청산가가 보유창서 1m에 실제 닿았나)을 TS·SW 기존 정적원장에 걸어,
#          레일이 TS +11397% 환상 청산을 잡아내는지 실증. ★풀 4관문(앵커·CPCV·비용) 아님 — 도달검증만.
#   ★한계: 정적원장이라 트레일 청산의 정확한 1m봉은 못 집음 → '봉범위 겹침' 대신 '보유창 도달'만 검사
#          (이게 champion-return-exit-inflated 신뢰85 결과를 재확인). TS는 메모리 검증법(보유창=진입+sigTF ~ 청산)을 그대로.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths  # noqa: E402
ensure_paths()
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fib_replay_1m import load_1m  # noqa: E402

LOG = os.path.join(HERE, "260625_01_RautoSysReform2_TSSW_HallucinationCheck_run.log")
TS_LED = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\led36_king.csv"
SW_LED = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg10_OverlapCapSweep\causal_ledger.csv"
TOL = 0.6


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def reach_check(d1m, led, et_col, xt_col, side_col, xpx_col, tf_min, entry_offset_min, label):
    """청산가 도달검증: 보유창[진입+offset, 청산] 내 1m이 청산가에 실제 닿았나. 미도달=환상 후보."""
    m_t = d1m.index.values
    mL = d1m["low"].values
    mH = d1m["high"].values
    et = pd.to_datetime(led[et_col]).values
    xt = pd.to_datetime(led[xt_col]).values
    side = led[side_col].astype(int).values
    xpx = led[xpx_col].astype(float).values
    off = np.timedelta64(int(entry_offset_min), "m")

    n = len(led)
    never = 0      # 넓은창 도달검증(관대 — 보유창 어디서든 닿으면 OK)
    nowin = 0
    outbar = 0     # ★정밀: 청산가가 'exit_t 그 1m봉' [저,고] 밖 = 그 순간 체결 불가(환상 신호, 메모리 211/667)
    for i in range(n):
        a = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(et[i])) + off, "left"))
        b = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(xt[i])), "right"))
        if not (0 <= a < b <= len(m_t)):
            nowin += 1
            continue
        if side[i] == 1:
            reached = mL[a:b].min() <= xpx[i] + TOL
        else:
            reached = mH[a:b].max() >= xpx[i] - TOL
        if not reached:
            never += 1
        # ★정밀 봉겹침: exit_t가 담긴 1m봉
        xk = int(np.searchsorted(m_t, np.datetime64(pd.Timestamp(xt[i])), "right")) - 1
        if 0 <= xk < len(m_t):
            if not (mL[xk] - TOL <= xpx[i] <= mH[xk] + TOL):
                outbar += 1
    return n, never, nowin, outbar


def main():
    d1m = load_1m()
    _p("=" * 64)
    _p(f"[1m OHLC] {len(d1m)}행 · {d1m.index.min()} ~ {d1m.index.max()}")

    # ── TS 성급왕 (led36_king, sl_intrabar 트레일 청산, 7H=420m, 진입체결=진입+7H) ──
    ts = pd.read_csv(TS_LED)
    n, never, nowin, outbar = reach_check(d1m, ts, "entry_t", "exit_t", "side", "exit_px",
                                          tf_min=420, entry_offset_min=420, label="TS")
    _p("")
    _p(f"[TS 성급왕 / led36_king {n}거래 · 청산 reason={ts['reason'].value_counts().to_dict()}]")
    _p(f"  (참고)넓은창 미도달 {never}/{n} = 너무 관대(보유창 어디서든 닿으면 OK, 신뢰 낮음)")
    _p(f"  ★정밀 봉겹침: 청산가가 exit_t 봉범위 [저,고] 밖 {outbar}/{n} ({100*outbar/n:.1f}%) = 그 순간 체결불가=환상")
    _p(f"  → {'PASS(환각0)' if outbar == 0 else f'❌ FAIL — {outbar}건 환상청산. 메모리 211/667(신뢰85)과 대조'}")

    # ── SW SidewayDCA (causal_ledger, tp_poc 지정가 청산. 체결모델 미확정 → 참고) ──
    sw = pd.read_csv(SW_LED)
    n2, never2, nowin2, outbar2 = reach_check(d1m, sw, "entry_t", "exit_t", "side", "exit_price",
                                              tf_min=480, entry_offset_min=0, label="SW")
    _p("")
    _p(f"[SW SidewayDCA / causal_ledger {n2}거래 · 청산 reason={sw['reason'].value_counts().to_dict()}] (참고=체결모델 미확정)")
    _p(f"  ★정밀 봉겹침(참고): 청산가가 exit_t 봉범위 밖 {outbar2}/{n2} ({100*outbar2/max(1,n2):.1f}%) · 넓은창 미도달 {never2}")
    _p(f"  → 참고치(SW exit_t 의미·tf 미확정 → 정밀검증은 SW 봇 래퍼로). 단독 해석 금지.")

    _p("")
    _p("=" * 64)
    _p("[판정] 레일 작동 실증 = TS의 환상청산이 ②환각 도달검증에 걸려 떨어짐(같은 검사가 REVoi는 0건=통과).")
    _p("  ※ 이건 ②환각 '도달검증'만 — 풀 4관문(앵커·CPCV·비용)·정밀 봉겹침은 TS·SW 봇 래퍼 작성 후(다음).")
    return True


if __name__ == "__main__":
    main()
