# -*- coding: utf-8 -*-
# [reexec_champion_1m_fills.py] 챔피언(R2 성급왕) 청산을 '1m 실체결'로 재실행 → 진짜 수익률 확정.
#   ★문제(코드 확증): king봇 bot_trendstack_impatient_king.py 72-73줄 = 1m 인트라바 손절가드가
#     'market.l<=self.sl'(롱) 터치 시 exit_px=self.sl(스톱 레벨)을 그대로 기록(봇 15줄 자인:
#     "SL 체결가는 SL 레벨로 기록, 슬리피지는 엔진 담당"=5bp 가정). 봉이 sl을 갭으로 뛰어넘으면
#     (open<sl) 실제 체결은 open(더 나쁨)인데 sl로 기록 → 수익 낙관적.
#   ★교정(§15-1 준수=봇 신호/트레일 로직 재구현 안함, 체결 물리만 교정):
#     기록된 sl(=exit_px)·exit_t는 그대로, 그 1m봉 실제가로 체결가 교체.
#       롱: 실체결 = min(open_exit, sl)  (open<sl 갭이면 open, 아니면 sl)
#       숏: 실체결 = max(open_exit, sl)
#     R_real = R_orig + side*(실체결 - sl)/entry * LEV. (sl 미변경 거래는 그대로)
#   ★원본 앵커 재현 후 교정본 대조(§15-2). 비용 5bp 스톱슬립·lev22·size_pct = bt36_ledgers와 동일.
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STG = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
for p in (os.path.join(STG, "bots"), STG):
    if p not in sys.path: sys.path.insert(0, p)
import rauto_paper_engine as PE
from rauto_contract import Signal, Action as A, Side

LED = os.path.join(STG, "led36_king.csv")
DATA = r"D:\ML\Verify\Merged_Data.csv"
LEV = 22.0


def _p(*a): print(*a, flush=True)


def main():
    L = pd.read_csv(LED)
    L["exit_t"] = pd.to_datetime(L["exit_t"], utc=True)
    m = pd.read_csv(DATA, usecols=["timestamp", "open", "high", "low"])
    m["t"] = pd.to_datetime(m["timestamp"], utc=True, format="ISO8601")
    m = m.set_index("t").sort_index()
    O, Hi, Lo = m["open"], m["high"], m["low"]

    real_exit, gap_n, deg = [], 0, []
    in_bar = 0
    for _, r in L.iterrows():
        sl, side, ent = float(r.exit_px), int(r.side), float(r.entry_px)
        if r.reason != "sl_intrabar":          # trend_flip 등은 종가체결=real, 교정 불필요
            real_exit.append(sl); deg.append(0.0); continue
        t = r.exit_t
        if t not in O.index:                    # 봉 없으면 보수적으로 원본 유지
            real_exit.append(sl); deg.append(0.0); continue
        o, h, l = float(O.loc[t]), float(Hi.loc[t]), float(Lo.loc[t])
        if l <= sl <= h: in_bar += 1            # sl이 봉 범위내=정상 체결
        re = min(o, sl) if side == 1 else max(o, sl)   # 갭이면 open(더 나쁨)
        if (side == 1 and o < sl) or (side == -1 and o > sl): gap_n += 1
        real_exit.append(re)
        deg.append(side * (re - sl) / ent)      # 체결 열화(음수=손해)
    L["real_exit"] = real_exit
    L["deg_ret"] = deg
    L["R_real"] = L["R"] + L["deg_ret"] * LEV
    # mae도 실체결이 더 나쁘면 갱신(보수)
    L["final_real"] = L["side"] * (L["real_exit"] - L["entry_px"]) / L["entry_px"]
    L["mae_real"] = np.minimum(L["mae"], L["final_real"])

    _p("=" * 78)
    _p("챔피언 R2 성급왕 — 청산 1m 실체결 재실행 (진짜 수익률 확정)")
    _p("=" * 78)
    _p(f"거래 {len(L)} | sl이 exit_t봉 범위내(정상체결): {in_bar} | 갭(sl 미존재→open체결): {gap_n}")
    _p(f"체결열화 분포(bp, 음수=손해): 중앙{np.median(L.deg_ret)*1e4:.0f} 평균{L.deg_ret.mean()*1e4:.0f} 최악{L.deg_ret.min()*1e4:.0f}")
    chg = L[L.deg_ret < -1e-9]
    _p(f"실제로 나빠진 거래: {len(chg)}건 | 그중 평균열화 {chg.deg_ret.mean()*1e4:.0f}bp(레버전)")

    def runbt(rcol, maecol):
        acct = PE.PaperAccount()
        for _, r in L.iterrows():
            acct.open(Signal(A.ENTER, side=Side(int(r.side)), size_pct=r.size_pct, leverage=LEV), ts=None, price=100.0)
            R = r[rcol] - (0.0005 if r.reason in ("sl", "sl_intrabar") else 0.0)
            acct.resolve_replay(R=R, mae=r[maecol], fund=r.fund)
        ret, mdd, _ = acct.metrics()
        return ret, mdd

    o_ret, o_mdd = runbt("R", "mae")
    r_ret, r_mdd = runbt("R_real", "mae_real")
    _p("-" * 78)
    _p(f"[원본 앵커]   k1.0 lev22 5bp: {o_ret:+.0f}% / MDD {o_mdd:.1f}%   (bt36_ledgers 재현)")
    _p(f"[1m 실체결]   k1.0 lev22 5bp: {r_ret:+.0f}% / MDD {r_mdd:.1f}%   ← 진짜")
    _p(f"[차이] 복리 {o_ret:.0f}% → {r_ret:.0f}%  (수익 {100*(r_ret-o_ret)/o_ret:+.1f}% 변화)")
    _p("-" * 78)
    # 연도별 R합 비교
    _p("연도별 R합(레버 후): 원본 vs 실체결")
    for y in sorted(L.year.unique()):
        s = L[L.year == y]
        _p(f"  {int(y)}: {s.R.sum():+.2f} → {s.R_real.sum():+.2f}  (Δ{(s.R_real.sum()-s.R.sum()):+.2f}, {len(s)}거래)")
    L.to_csv(os.path.join(HERE, "champion_reexec_1m.csv"), index=False, encoding="utf-8-sig")
    _p(f"\n[저장] champion_reexec_1m.csv")
    _p("[정직] 진입은 검증완료(100% 7H창내 실존). 이 교정은 sl_intrabar 청산만 실체결로. trend_flip/진입 불변.")
    _p("[경계] open 체결도 낙관일수있음(갭 중간체결 더나쁠수). 진짜 하한은 틱데이터. 5bp 스톱슬립은 유지(이중계산 회피).")


if __name__ == "__main__":
    main()
