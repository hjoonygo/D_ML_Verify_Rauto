# -*- coding: utf-8 -*-
# [report_gross_net.py] 무비용(낙관) vs 실비용(현실) 수익 — 거래비용(수수료+펀딩+슬리피지)을 빼면 '이전 수익' 규모.
#   무비용 = 이론 스톱레벨(x_int) 체결 + 수수료0 + 펀딩0 (=엔진식 낙관 백테).
#   실비용 = 1m 실체결(갭) + 수수료6bp + 실펀딩 (=현실). 둘 다 동일 mae로 강제청산(격리마진) 적용 → 비용효과만 분리.
import sys, os
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = dict(sig_tf=240, pivot_tf=5, N=9, fib=(0.4363, 0.5576, 0.7447), init_atr_mult=2.969, er_gate=0.0567, size_pct=7.864, lev=10.238)
START = 10000.0


def _p(*a): print(*a, flush=True)


def main():
    d1m = load_1m(); fund = load_funding()
    T = B.gen_trades(d1m, fund, CFG["sig_tf"], CFG["pivot_tf"], CFG["N"], CFG["fib"],
                     CFG["init_atr_mult"], er_gate=CFG["er_gate"]).sort_values("et").reset_index(drop=True)
    ag = PE.PaperAccount(START); am = PE.PaperAccount(START); an = PE.PaperAccount(START); rows = []
    for _, r in T.iterrows():
        side = int(r.side)
        R_gross = side * (float(r.x_int) - float(r.entry)) / float(r.entry)   # ①낙관: 이론 스톱레벨 체결·수수료0·펀딩0
        R_mid = side * (float(r.exit) - float(r.entry)) / float(r.entry)      # ②실체결 유지·수수료/펀딩만 제거
        R_net = float(r.R)                                                    # ③현실: 1m체결+수수료+펀딩
        bg = ag.bal; bm = am.bal; bn = an.bal
        for acc, R, fd in [(ag, R_gross, 0.0), (am, R_mid, 0.0), (an, R_net, float(r.fund))]:
            acc.open(Signal(Action.ENTER, side=Side(side), size_pct=CFG["size_pct"], leverage=CFG["lev"]), ts=None, price=100.0)
            acc.resolve_replay(R=R, mae=float(r.mae), fund=fd)
        rows.append(dict(month=pd.Timestamp(r.et).strftime("%Y-%m"), pg=ag.bal - bg, pm=am.bal - bm, pn=an.bal - bn))
    L = pd.DataFrame(rows)
    rg, mg, _ = ag.metrics(); rm, mm, _ = am.metrics(); rn, mn, _ = an.metrics()

    _p("█" * 86)
    _p("무비용(낙관) vs 실비용(현실) 수익 — 거래비용을 빼면 '이전 수익' 규모")
    _p("█" * 86)
    _p(f"[모델] 4h신호+5m눌림목 피보 · lev{CFG['lev']:.1f} · 증거금{CFG['size_pct']:.2f}% · 격리마진 · 시작${START:,.0f}")
    _p("[무비용] 이론 스톱레벨 체결 + 수수료0 + 펀딩0 (=엔진식 낙관)  [실비용] 1m실체결+수수료6bp+실펀딩")
    _p(f"\n{'월':<9}{'①낙관수익$':>13}{'①낙관누적$':>14}{'③현실수익$':>12}{'③현실누적$':>13}")
    _p("-" * 64)
    cg = cn = 0.0
    for m, g in L.groupby("month"):
        sg = g.pg.sum(); sn = g.pn.sum(); cg += sg; cn += sn
        _p(f"{m:<9}{sg:>+13.0f}{cg:>+14.0f}{sn:>+12.0f}{cn:>+13.0f}")
    _p("-" * 64)
    _p(f"{'합계':<9}{L.pg.sum():>+13.0f}{'':>14}{L.pn.sum():>+12.0f}{'':>13}")
    _p("\n" + "=" * 86)
    _p("3단계 분해 (시작 $10,000):")
    _p(f"  ① 낙관(이론 스톱레벨 체결·무수수료·무펀딩) : {rg:+,.0f}% → ${ag.bal:,.0f}   [달성불가 환상]")
    _p(f"  ② 실체결 유지·수수료/펀딩만 제거          : {rm:+.1f}% → ${am.bal:,.0f}")
    _p(f"  ③ 현실(1m실체결+수수료6bp+실펀딩)         : {rn:+.1f}% → ${an.bal:,.0f}")
    _p("-" * 86)
    _p(f"  ★진짜 거래비용(수수료+펀딩)이 먹은 양 = ②−③ = ${am.bal-an.bal:,.0f}  ← 이게 '실제 거래비용 빼면 더해질' 정직한 양")
    _p(f"  ★①−② = ${ag.bal-am.bal:,.0f} = '스톱이 시장 위에 놓여 이론가 체결' 가정의 환상분(실제론 못 받는 가격)")
    _p(f"[정직] '이전 수익 {rg:+,.0f}%'는 거의 전부 ①−②(체결 환상)이지 거래비용이 아님. 진짜 거래비용은 ${am.bal-an.bal:,.0f}로 미미.")
    _p("       ⚠️ ①이 이렇게 큰 건 하니스가 참조고점(4h)과 스텝업 눌림목(5m)을 섞어 스톱을 높이 놓은 영향 — 환상의 교과서 사례.")
    L.to_csv(os.path.join(HERE, "gross_net_monthly.csv"), index=False, encoding="utf-8-sig")
    _p("[저장] gross_net_monthly.csv")


if __name__ == "__main__":
    main()
