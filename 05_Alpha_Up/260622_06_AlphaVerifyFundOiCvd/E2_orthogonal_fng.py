# -*- coding: utf-8 -*-
# [E2_orthogonal_fng.py] 알파 향상 실험 2 — '직교 도메인' 가설 검증.
#   E1 교훈: OI×모멘텀(둘다 파생/가격=중복)은 향상 실패. 문헌=서로 다른 *도메인* 결합이 알파.
#   → 센티먼트(Fear&Greed)는 파생/가격과 부분직교한 역추세 방향신호. mom·OI에 붙이면 향상되나?
#   ★F&G=일별 contrarian(극단탐욕→반전하락, 극단공포→반전상승). asof backward=t에 알려진 값(룩어헤드0).
#   검증: alpha_verification_system 3단 + mom_24h(현 최강 베이스) 대비.
import os
import numpy as np, pandas as pd
import alpha_verification_system as AV

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def _p(*a): print(*a, flush=True)


def main():
    P = AV.build_panel().sort_index()
    P["mom_24h"] = P["open"].pct_change(3)
    # Fear&Greed (unix초 일별) → 8h 그리드 asof backward
    fg = pd.read_csv(os.path.join(ROOT, "Fear_Greed_Index_2018to20260602.csv"))
    fg["t"] = pd.to_datetime(fg["timestamp"].astype(int), unit="s", utc=True)
    fg = fg.dropna(subset=["value"]).drop_duplicates("t").sort_values("t")
    fg["value"] = pd.to_numeric(fg["value"], errors="coerce")
    pidx = pd.DataFrame({"t": P.index}).sort_values("t")
    merged = pd.merge_asof(pidx, fg[["t", "value"]], on="t", direction="backward",
                           tolerance=pd.Timedelta(days=2))
    P["fng"] = merged.set_index("t")["value"].reindex(P.index).values
    P["fng_c"] = (P["fng"] - 50.0) / 50.0       # 중심화 -1(극공포)~+1(극탐욕)

    # 직교 조합
    P["fng_x_mom"] = P["mom_24h"] * P["fng_c"]   # 확장×탐욕 = 과열 반전셋업
    P["fng_x_oi"] = P["oi_z"] * P["fng_c"]       # OI과열×탐욕 = 이중확신 반전
    P["mom_x_oi_x_fng"] = P["mom_24h"] * P["oi_z"].abs() * P["fng_c"].abs() * np.sign(P["fng_c"])

    oimask = P["oi_z"].notna() & P["fng"].notna()
    Poi = P[oimask]
    fwd = Poi["fwd_8h"]
    _p(f"[F&G 커버] 패널 {len(P)} 중 F&G유효 {P['fng'].notna().sum()} | OI∩F&G {len(Poi)}")

    SIGS = [
        ("mom_24h (현 최강 베이스)", Poi["mom_24h"]),
        ("oi_z (파생 단독)", Poi["oi_z"]),
        ("fng (센티먼트 단독)", Poi["fng"]),
        ("◆fng×mom (직교: 센티+가격)", Poi["fng_x_mom"]),
        ("◆fng×OI (직교: 센티+파생)", Poi["fng_x_oi"]),
        ("◆mom×OI×fng (3도메인)", Poi["mom_x_oi_x_fng"]),
    ]
    N = len(SIGS)
    _p("\n" + "=" * 96)
    _p("E2: 직교 도메인(Fear&Greed) 결합 — 향상되나? (2023-26, 비용 8bp)")
    _p("=" * 96)
    _p(f"{'신호':<28}{'IC':>8}{'방향':>5}{'WF안정':>7}{'net SR':>8}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'②엣지':>6}{'③배포':>6}")
    _p("-" * 96)
    rows = []
    for nm, s in SIGS:
        r = AV.verify_signal(nm, s, fwd, n_trials=N)
        _p(f"{nm:<28}{r['ic']:>+8.3f}{'+' if r['direction']>0 else '-':>5}"
           f"{r['wf']['sign_stability']:>6.0%}{r['net_sharpe']:>8.2f}{r['cpcv']['p25']:>10.2f}"
           f"{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}"
           f"{'O' if r['edge_confirmed'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")
        rows.append(dict(sig=nm, ic=r['ic'], wf=r['wf']['sign_stability'], net_sharpe=r['net_sharpe'],
                         cpcv_p25=r['cpcv']['p25'], dsr=r['dsr']['dsr'], possibility=r['possibility'],
                         edge=r['edge_confirmed'], deployable=r['deployable']))
    D = pd.DataFrame(rows); D.to_csv(os.path.join(HERE, "E2_results.csv"), index=False, encoding="utf-8-sig")
    base = D[D.sig.str.contains("단독|베이스")]; orth = D[D.sig.str.contains("◆")]
    _p("-" * 96)
    _p(f"[베이스 최고]  WF {base.wf.max():.0%} / net SR {base.net_sharpe.max():.2f}")
    _p(f"[직교조합 최고] WF {orth.wf.max():.0%} / net SR {orth.net_sharpe.max():.2f}")
    win = orth.net_sharpe.max() > base.net_sharpe.max() and orth.wf.max() >= base.wf.max()
    _p(f"[판정] 직교조합이 베이스 초과? {'예(향상 증거)' if win else '아니오(이 센티먼트로도 미향상)'}")
    _p("[정직] F&G는 부분직교(여전히 가격/변동성 성분 포함). 진짜 직교=온체인(MVRV/netflow)·매크로. IC≠수익.")


if __name__ == "__main__":
    main()
