# -*- coding: utf-8 -*-
# [E3_orthogonal_ensemble.py] 직교 세트 덧셈 앙상블 — 측정이 찾아준 직교지표를 '곱'이 아닌 '합'으로.
#   직교성 측정 결과: mom_24h(가격)·oi_z(포지셔닝)·fund_slope(펀딩흐름) = 상호 저상관 + 증분IC 보유.
#   ★올바른 조합 = 각 신호를 IC방향으로 정렬·표준화 후 '덧셈'(앙상블). E1의 곱셈(상호작용)이 틀린 방법이었음.
#   검증: alpha_verification_system 3단 + mom_24h 단독(현 최강) 대비.
import os
import numpy as np, pandas as pd
from scipy import stats
import alpha_verification_system as AV

HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a): print(*a, flush=True)


def zr(s):   # 랭크 표준화(중심0, 강건)
    return s.rank(pct=True) - 0.5


def main():
    P = AV.build_panel().sort_index()
    P["mom_24h"] = P["open"].pct_change(3)
    # fund_slope, oi_z 는 패널에 이미 있음
    win = P[["mom_24h", "oi_z", "fund_slope", "fwd_8h"]].dropna()
    _p(f"[표본] {len(win)} (OI 가용창)")

    def ic(x, y):
        m = x.notna() & y.notna(); return stats.spearmanr(x[m], y[m])[0]
    comps = ["mom_24h", "oi_z", "fund_slope"]
    sign = {c: np.sign(ic(win[c], win["fwd_8h"])) or 1.0 for c in comps}
    _p("  성분 IC방향: " + ", ".join(f"{c}={'+' if sign[c]>0 else '-'}({ic(win[c],win['fwd_8h']):+.3f})" for c in comps))

    # IC방향 정렬 후 덧셈 앙상블
    a = {c: zr(win[c]) * sign[c] for c in comps}     # 전부 '+방향=고수익' 정렬
    win["ens_mom_oi"] = a["mom_24h"] + a["oi_z"]
    win["ens_mom_fs"] = a["mom_24h"] + a["fund_slope"]
    win["ens_oi_fs"] = a["oi_z"] + a["fund_slope"]
    win["ens_all3"] = a["mom_24h"] + a["oi_z"] + a["fund_slope"]

    SIGS = [
        ("mom_24h (단독 베이스)", win["mom_24h"]),
        ("oi_z (단독)", win["oi_z"]),
        ("fund_slope (단독)", win["fund_slope"]),
        ("◆ens mom+oi", win["ens_mom_oi"]),
        ("◆ens mom+fundslope", win["ens_mom_fs"]),
        ("◆ens oi+fundslope", win["ens_oi_fs"]),
        ("◆◆ens all3 (직교 앙상블)", win["ens_all3"]),
    ]
    N = len(SIGS); fwd = win["fwd_8h"]
    _p("\n" + "=" * 96)
    _p("E3: 직교 세트 덧셈 앙상블 — 검증시스템 3단 (vs mom_24h 단독)")
    _p("=" * 96)
    _p(f"{'신호':<26}{'IC':>8}{'방향':>5}{'WF안정':>7}{'net SR':>8}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'②엣지':>6}{'③배포':>6}")
    _p("-" * 96)
    rows = []
    for nm, s in SIGS:
        r = AV.verify_signal(nm, s, fwd, n_trials=N)
        _p(f"{nm:<26}{r['ic']:>+8.3f}{'+' if r['direction']>0 else '-':>5}"
           f"{r['wf']['sign_stability']:>6.0%}{r['net_sharpe']:>8.2f}{r['cpcv']['p25']:>10.2f}"
           f"{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}"
           f"{'O' if r['edge_confirmed'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")
        rows.append(dict(sig=nm, ic=r['ic'], wf=r['wf']['sign_stability'], net_sharpe=r['net_sharpe'],
                         cpcv_p25=r['cpcv']['p25'], dsr=r['dsr']['dsr'], info_sharpe=r['info_sharpe'],
                         possibility=r['possibility'], edge=r['edge_confirmed'], deployable=r['deployable']))
    D = pd.DataFrame(rows); D.to_csv(os.path.join(HERE, "E3_results.csv"), index=False, encoding="utf-8-sig")
    b = D[D.sig.str.contains("단독")]; e = D[D.sig.str.contains("◆")]
    _p("-" * 96)
    _p(f"[단독 최고]   WF {b.wf.max():.0%} / net SR {b.net_sharpe.max():.2f} / info SR {b.info_sharpe.max():.2f}")
    _p(f"[앙상블 최고] WF {e.wf.max():.0%} / net SR {e.net_sharpe.max():.2f} / info SR {e.info_sharpe.max():.2f}")
    win_flag = (e.net_sharpe.max() > b.net_sharpe.max()) and (e.wf.max() >= b.wf.max())
    _p(f"[판정] 직교 덧셈 앙상블이 단독 초과? {'예(향상 증거·덧셈이 곱셈보다 옳음)' if win_flag else '아니오'}")
    _p("[정직] 2023-26·비용8bp. 향상 보여도 ②엣지/③배포는 별개. 장기 직교(온체인/매크로)는 아직 미포함.")


if __name__ == "__main__":
    main()
