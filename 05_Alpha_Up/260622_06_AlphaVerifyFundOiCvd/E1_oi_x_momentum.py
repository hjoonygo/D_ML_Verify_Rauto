# -*- coding: utf-8 -*-
# [E1_oi_x_momentum.py] 알파 향상 실험 1 — "OI(확신) × 모멘텀(방향)" 조합이 단독보다 살아나나?
#   가설(문헌): OI는 방향이 아니라 '확신/에너지'. 방향(모멘텀)에 OI를 붙이면 continuation/exhaustion이 갈림.
#     mom↑ & OI↑ = 추세지속(롱) / mom↑ & OI↓ = 소진·반전(숏) / mom↓ & OI↑ = 하락지속(숏) / mom↓ & OI↓ = 숏커버(롱)
#     → combo = mom × sign(ΔOI)  (이 부호논리를 한 신호에 인코딩; 검증시스템이 방향 자동발견)
#   검증: 방금 만든 alpha_verification_system 3단(①가능성 ②엣지 ③배포)에 베이스라인과 함께 통과.
#   ★룩어헤드 0: mom=과거수익(open pct_change), ΔOI=oi_z.diff()(이미 shift1). 전부 t에 알려진 값.
import os
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import alpha_verification_system as AV

HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a): print(*a, flush=True)


def main():
    P = AV.build_panel()                      # fund, open, close, oi_z, fund_slope, fwd_8h
    P = P.sort_index()
    # 방향(모멘텀) = 과거수익 (t에 알려짐)
    P["mom_8h"] = P["open"].pct_change(1)      # 직전 8h
    P["mom_24h"] = P["open"].pct_change(3)     # 직전 24h
    P["mom_72h"] = P["open"].pct_change(9)     # 직전 3일
    # 확신(OI 변화) = ΔOI z (상승=신규자금/확신, 하락=청산/소진)
    P["d_oi"] = P["oi_z"].diff()
    s_doi = np.sign(P["d_oi"]).replace(0, np.nan).ffill().fillna(1.0)
    # 조합 신호 (continuation/exhaustion 인코딩)
    P["combo_8h"] = P["mom_8h"] * s_doi
    P["combo_24h"] = P["mom_24h"] * s_doi
    P["combo_72h"] = P["mom_72h"] * s_doi
    # OI 확신 게이트형(모멘텀을 OI상승때만 = continuation 전용)
    P["gated_24h"] = np.where(P["d_oi"] > 0, P["mom_24h"], 0.0)
    # ★교정 조합 v2: 8h는 역추세(reversion)라 'OI 극단 수준'으로 되돌림 증폭 (노이즈 ΔOI부호 대신)
    P["mr_absOI"] = P["mom_24h"] * P["oi_z"].abs()       # 확장×OI과열도(극단일수록 강한 되돌림)
    P["mr_OI"] = P["mom_24h"] * P["oi_z"]                # 부호있는 상호작용(상승+과열=숏셋업)
    P["mom24_OIhi"] = np.where(P["oi_z"].abs() > 1.0, P["mom_24h"], 0.0)  # OI 극단일때만 fade

    # OI 가용창(2023~)으로 공정비교 (combo가 oi 필요)
    oimask = P["oi_z"].notna()
    Poi = P[oimask]

    SIGS = [
        ("mom_8h (단기방향 단독)", Poi["mom_8h"]),
        ("mom_24h (중기방향 단독)", Poi["mom_24h"]),
        ("mom_72h (장기방향 단독)", Poi["mom_72h"]),
        ("oi_z (OI확신 단독)", Poi["oi_z"]),
        ("★combo_8h = mom8×ΔOI", Poi["combo_8h"]),
        ("★combo_24h = mom24×ΔOI", Poi["combo_24h"]),
        ("★combo_72h = mom72×ΔOI", Poi["combo_72h"]),
        ("gated_24h (OI상승때만 mom)", Poi["gated_24h"]),
        ("◆mr_absOI = mom24×|OIz|", Poi["mr_absOI"]),
        ("◆mr_OI = mom24×OIz", Poi["mr_OI"]),
        ("◆mom24_OIhi (OI극단때만 fade)", Poi["mom24_OIhi"]),
    ]
    N = len(SIGS)
    fwd = Poi["fwd_8h"]

    _p("\n" + "=" * 100)
    _p("E1: OI(확신) × 모멘텀(방향) 조합 — 검증시스템 3단 (2023-26 OI가용창, 비용 왕복8bp)")
    _p("=" * 100)
    _p(f"{'신호':<26}{'IC':>8}{'방향':>5}{'WF안정':>7}{'net SR':>8}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'②엣지':>6}{'③배포':>6}")
    _p("-" * 100)
    rows = []
    for nm, s in SIGS:
        r = AV.verify_signal(nm, s, fwd, n_trials=N)
        _p(f"{nm:<26}{r['ic']:>+8.3f}{'+' if r['direction']>0 else '-':>5}"
           f"{r['wf']['sign_stability']:>6.0%}{r['net_sharpe']:>8.2f}{r['cpcv']['p25']:>10.2f}"
           f"{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}"
           f"{'O' if r['edge_confirmed'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")
        rows.append(dict(sig=nm, ic=r['ic'], wf=r['wf']['sign_stability'], net_sharpe=r['net_sharpe'],
                         info_sharpe=r['info_sharpe'], cpcv_p25=r['cpcv']['p25'], dsr=r['dsr']['dsr'],
                         possibility=r['possibility'], edge=r['edge_confirmed'], deployable=r['deployable']))
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(HERE, "E1_results.csv"), index=False, encoding="utf-8-sig")

    # 비교 그래프: net Sharpe + WF안정 (combo가 baseline 이기나)
    fig, ax = plt.subplots(1, 2, figsize=(15, 5.5))
    cols = ["#2a6" if "◆" in s else ("#258" if ("combo" in s or "gated" in s) else "#999") for s in D["sig"]]
    ax[0].barh(range(len(D)), D["net_sharpe"], color=cols); ax[0].set_yticks(range(len(D))); ax[0].set_yticklabels([s.replace('★','') for s in D["sig"]], fontsize=8)
    ax[0].axvline(0, color="k", lw=.8); ax[0].set_title("net Sharpe (cost-adj, blue=combo/gated)"); ax[0].set_xlabel("annual Sharpe")
    ax[1].barh(range(len(D)), D["wf"], color=cols); ax[1].set_yticks(range(len(D))); ax[1].set_yticklabels([s.replace('★','') for s in D["sig"]], fontsize=8)
    ax[1].axvline(0.625, color="#e80", ls="--", label="possibility gate"); ax[1].set_xlim(0, 1); ax[1].legend(fontsize=8)
    ax[1].set_title("WF sign stability")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "E1_combo_vs_baseline.png"), dpi=110); plt.close(fig)

    # 핵심 대조 요약
    _p("-" * 100)
    base = D[D.sig.str.contains("단독")][["sig", "net_sharpe", "wf", "info_sharpe"]]
    cmb = D[D.sig.str.contains("combo|gated")][["sig", "net_sharpe", "wf", "info_sharpe"]]
    _p(f"[베이스 최고 net SR] {base.net_sharpe.max():.2f} / [조합 최고 net SR] {cmb.net_sharpe.max():.2f}")
    _p(f"[베이스 최고 WF안정] {base.wf.max():.0%} / [조합 최고 WF안정] {cmb.wf.max():.0%}")
    _p(f"[저장] E1_results.csv + E1_combo_vs_baseline.png")
    _p("[해석] 조합(파랑)이 베이스(회색)보다 WF안정·net SR↑면 = 'OI확신×방향'이 단독보다 살아남(알파 가능성→향상 증거).")
    _p("[정직] 2023-26·비용8bp·IC≠수익. 향상 보여도 ②엣지/③배포는 별개 관문. 장기(온체인)는 미포함(데이터필요).")


if __name__ == "__main__":
    main()
