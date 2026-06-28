# -*- coding: utf-8 -*-
# [orthogonality_analysis.py] 직교성 '측정' — 지표 차원에도 적용 (캡틴 지시 2026-06-22).
#   "성격이 다르다"는 가정이 아니라 측정으로 도토리 키재기(중복)를 걸러낸다.
#   ① 신호 간 Spearman 상관행렬 → 같은뿌리 클러스터(|corr|↑) 식별.
#   ② ★증분 예측력(incremental IC): 지표 B를 기준지표 A로 잔차화(residualize) 후, 그 잔차가
#      선행수익을 여전히 예측하나? 잔차IC≈0=중복(도토리), 잔차IC 유효=직교 기여.
#   = 진짜 직교 = (낮은 상관) AND (증분 예측력 있음). 둘 다여야 조합 가치.
import os
import numpy as np, pandas as pd
from scipy import stats
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import alpha_verification_system as AV

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
H8 = 8 * 3600 * 1000


def _p(*a): print(*a, flush=True)


def load_cvd_z_8h(P):
    c = pd.read_csv(os.path.join(ROOT, "CVD_15m_BTCUSDT.csv"), usecols=["timestamp", "delta"])
    c["t"] = pd.to_datetime(c["timestamp"], utc=True, format="ISO8601") + pd.Timedelta(minutes=15)
    c = c.dropna().sort_values("t")
    net = c["delta"].astype(float)
    c7 = net.rolling(28, min_periods=14).sum()
    z = (c7 - c7.rolling(1120, min_periods=200).mean()) / (c7.rolling(1120, min_periods=200).std() + 1e-9)
    cz = pd.DataFrame({"t": c["t"], "cvd_z": z.values}).dropna()
    m = pd.merge_asof(pd.DataFrame({"t": P.index}).sort_values("t"), cz, on="t", direction="backward",
                      tolerance=pd.Timedelta(minutes=20))
    return m.set_index("t")["cvd_z"].reindex(P.index).values


def main():
    P = AV.build_panel().sort_index()
    P["mom_8h"] = P["open"].pct_change(1)
    P["mom_24h"] = P["open"].pct_change(3)
    P["mom_72h"] = P["open"].pct_change(9)
    P["d_oi"] = P["oi_z"].diff()
    fg = pd.read_csv(os.path.join(ROOT, "Fear_Greed_Index_2018to20260602.csv"))
    fg["t"] = pd.to_datetime(fg["timestamp"].astype(int), unit="s", utc=True)
    fg["value"] = pd.to_numeric(fg["value"], errors="coerce")
    fgm = pd.merge_asof(pd.DataFrame({"t": P.index}).sort_values("t"), fg[["t", "value"]].dropna().sort_values("t"),
                        on="t", direction="backward", tolerance=pd.Timedelta(days=2))
    P["fng"] = fgm.set_index("t")["value"].reindex(P.index).values
    P["cvd_z"] = load_cvd_z_8h(P)

    SIG = ["mom_8h", "mom_24h", "mom_72h", "oi_z", "d_oi", "fund", "fund_slope", "cvd_z", "fng"]
    D = P[SIG + ["fwd_8h"]].dropna()
    _p(f"[패널] 직교성 측정 표본 {len(D)} (전 지표·F&G·CVD 교집합)")

    # ① 상관행렬 (Spearman, 신호값끼리)
    R = D[SIG].rank()
    C = R.corr(method="pearson")   # rank상관=Spearman
    _p("\n① 신호 간 상관행렬 (|corr|>=0.5 = 같은뿌리 도토리 의심)")
    _p("        " + "".join(f"{s[:7]:>8}" for s in SIG))
    for i, s in enumerate(SIG):
        _p(f"{s:>8}" + "".join(f"{C.iloc[i,j]:>8.2f}" for j in range(len(SIG))))

    # ② 각 지표 단독 IC + mom_24h 기준 증분(잔차) IC
    def ic(x, y):
        m = x.notna() & y.notna()
        return stats.spearmanr(x[m], y[m])[0] if m.sum() > 30 else np.nan
    base = "mom_24h"
    rb = D[base].rank()
    _p(f"\n② 단독 IC vs ★증분 IC(기준 {base}로 잔차화 후) — 잔차IC≈0=도토리, 유효=직교기여")
    rows = []
    for s in SIG:
        ic_solo = ic(D[s], D["fwd_8h"])
        if s == base:
            inc = ic_solo; corr_b = 1.0
        else:
            rs = D[s].rank()
            beta = np.polyfit(rb, rs, 1)[0]
            resid = rs - beta * rb            # mom_24h로 설명 안 되는 부분
            inc = stats.spearmanr(resid, D["fwd_8h"].rank())[0]
            corr_b = C.loc[base, s]
        tag = "직교기여" if (abs(corr_b) < 0.4 and abs(inc) >= 0.02) else ("도토리(중복)" if abs(corr_b) >= 0.4 else "약함")
        _p(f"  {s:<11} 단독IC {ic_solo:+.3f} | {base}상관 {corr_b:+.2f} | 증분IC {inc:+.3f}  → {tag}")
        rows.append(dict(sig=s, ic_solo=ic_solo, corr_base=corr_b, inc_ic=inc, verdict=tag))
    DF = pd.DataFrame(rows); DF.to_csv(os.path.join(HERE, "orthogonality_results.csv"), index=False, encoding="utf-8-sig")

    # 그래프: 상관 히트맵 + 증분IC 막대
    fig, ax = plt.subplots(1, 2, figsize=(15, 6))
    im = ax[0].imshow(C.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax[0].set_xticks(range(len(SIG))); ax[0].set_xticklabels(SIG, rotation=45, ha="right", fontsize=8)
    ax[0].set_yticks(range(len(SIG))); ax[0].set_yticklabels(SIG, fontsize=8)
    for i in range(len(SIG)):
        for j in range(len(SIG)):
            ax[0].text(j, i, f"{C.iloc[i,j]:.1f}", ha="center", va="center", fontsize=7,
                       color="white" if abs(C.iloc[i,j]) > 0.5 else "black")
    ax[0].set_title("Signal correlation (Spearman) — clusters = redundant"); fig.colorbar(im, ax=ax[0], fraction=0.046)
    cols = ["#2a6" if v == "직교기여" else ("#c44" if "도토리" in v else "#999") for v in DF["verdict"]]
    ax[1].barh(DF["sig"], DF["inc_ic"], color=cols); ax[1].axvline(0, color="k", lw=.8)
    ax[1].axvline(0.02, color="#e80", ls="--"); ax[1].axvline(-0.02, color="#e80", ls="--")
    ax[1].set_title(f"Incremental IC after residualizing on {base}\n(green=orthogonal contribution, red=redundant)")
    ax[1].set_xlabel("residual IC vs fwd_8h")
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "orthogonality_map.png"), dpi=110); plt.close(fig)
    _p("\n[저장] orthogonality_results.csv + orthogonality_map.png")
    _p("[규칙] 조합 가치 = (기준상관 |r|<0.4) AND (증분IC |x|>=0.02). 둘 다여야 직교기여. 측정으로 도토리 자동배제.")


if __name__ == "__main__":
    main()
