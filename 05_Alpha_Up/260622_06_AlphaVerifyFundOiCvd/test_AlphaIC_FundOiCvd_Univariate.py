# -*- coding: utf-8 -*-
# [test_AlphaIC_FundOiCvd_Univariate.py]
# 목적: Funding / OI / CVD 3계열 피처의 '단변량 예측력(IC)' 사전스크리닝.
#   ★이건 백테가 아니다(PF/MDD/수익률 주장 금지). '피처→선행수익 상관'만 측정하는 진단.
#   합격 시에만 후속 검증엔진 백테(§15)로 넘어간다.
#
# 절대 문제없을 방법(캡틴 지시 2026-06-22):
#   (1) 룩어헤드 0: 모든 피처 merge_asof(backward)=과거값만. 종가는 15m '마감시각' 정렬(15분 선반영 차단).
#   (2) 비중첩 유의성: 스파인=펀딩 8h 정산시각 → 8h 선행수익이 자동 비중첩. 24h는 비중첩 일별 서브샘플 병행.
#   (3) 강건 IC: Spearman(순위상관, 비정규/이상치 강건) + p값. 5분위 단조성표로 경제적의미 확인.
#   (4) 데이터 무결성: 펀딩은 '진짜 변동' 파일(BTCUSDT_funding_history_8h.csv) 사용.
#       ★BTCUSDT_funding_rates_23_26.csv는 fundingRate 전부 0.0001 고정(손상) → 사용 금지.
#   (5) cvd_z = 라이브 계보(test_Rauto_cvd.py 39~43줄: net=taker_buy-taker_sell, 7h롤링합, W=40배창 인과z)
#       를 15m 그리드에 재현(§15-2 앵커 동치).
#   (6) 다중검정: 사전등록 5피처×2호라이즌=10검정. 스크린이지 확정아님(Deflated Sharpe 정신).
#
# 데이터(전부 2023-05-01 ~ 2026-04-30 = 36개월):
#   ../BTCUSDT_funding_history_8h.csv  : fundingTime,fundingRate,markPrice_at_funding (3288행)
#   ../CVD_15m_BTCUSDT.csv             : timestamp,open,high,low,close,volume,taker_buy,delta (105216행)
#   ../Merged_Data.csv (REPAIRED 계보) : timestamp,close,oi_zscore_24h,oi_change_1h_pct (1,578,240행 1m)
import os
import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))   # D:\ML\Verify (self-locating)


def _p(*a):
    print(*a, flush=True)


def load_funding():
    f = pd.read_csv(os.path.join(ROOT, "BTCUSDT_funding_history_8h.csv"))
    f["t"] = pd.to_datetime(f["fundingTime"], utc=True, format="ISO8601")
    f["fundingRate"] = pd.to_numeric(f["fundingRate"], errors="coerce")
    f = f.dropna(subset=["fundingRate"]).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    # 무결성 가드: 펀딩이 상수면 손상파일 → 즉시 중단
    if f["fundingRate"].std() < 1e-9:
        raise ValueError("펀딩비가 상수(손상파일). BTCUSDT_funding_history_8h.csv 확인 필요.")
    f["fund_level"] = f["fundingRate"]
    f["fund_slope"] = f["fundingRate"].diff()           # 직전 8h 대비 변화(과거-과거, 룩어헤드 없음)
    return f[["t", "fund_level", "fund_slope"]]


def load_cvd_price():
    """CVD 15m → (a) 라이브계보 cvd_z(인과), (b) 마감시각 종가 스파인."""
    c = pd.read_csv(os.path.join(ROOT, "CVD_15m_BTCUSDT.csv"),
                    usecols=["timestamp", "close", "delta"])
    c["t_open"] = pd.to_datetime(c["timestamp"], utc=True, format="ISO8601")
    c = c.dropna(subset=["close"]).drop_duplicates("t_open").sort_values("t_open").reset_index(drop=True)
    c["t_close"] = c["t_open"] + pd.Timedelta(minutes=15)   # 마감시각(이 종가는 이때 실현)
    # --- cvd_z (라이브 계보 재현: 1m 420분합/W=40배 → 15m로 28봉합/1120봉창) ---
    net = c["delta"].astype(float)                          # = taker_buy - taker_sell (15m)
    c7 = net.rolling(28, min_periods=14).sum()             # 7h 롤링합
    W = 28 * 40                                            # =1120봉(=11.67일) 평균/표준편차창
    mu = c7.rolling(W, min_periods=200).mean()
    sd = c7.rolling(W, min_periods=200).std()
    c["cvd_z"] = (c7 - mu) / (sd + 1e-9)                    # 전부 backward=인과
    return c[["t_open", "t_close", "close", "cvd_z"]]


def load_oi():
    cols = ["timestamp", "oi_zscore_24h", "oi_change_1h_pct"]
    d = pd.read_csv(os.path.join(ROOT, "Merged_Data.csv"), usecols=cols)
    d["t"] = pd.to_datetime(d["timestamp"], utc=True, format="ISO8601")
    for c in ["oi_zscore_24h", "oi_change_1h_pct"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["t"]).sort_values("t").reset_index(drop=True)[["t", "oi_zscore_24h", "oi_change_1h_pct"]]


def build_panel():
    fund = load_funding()
    cvd = load_cvd_price()
    oi = load_oi()

    spine = fund.copy()   # t = 펀딩 정산시각(8h)
    # --- 종가: 15m '마감시각' 기준 backward asof (마감시각<=t 인 마지막 봉) → 15분 룩어헤드 차단 ---
    px = cvd[["t_close", "close"]].rename(columns={"t_close": "t"}).sort_values("t")
    spine = pd.merge_asof(spine, px, on="t", direction="backward",
                          tolerance=pd.Timedelta(minutes=20))
    # --- cvd_z: 봉 마감시각 기준 backward (마감된 봉의 인과z만) ---
    cz = cvd[["t_close", "cvd_z"]].rename(columns={"t_close": "t"}).sort_values("t")
    spine = pd.merge_asof(spine, cz, on="t", direction="backward",
                          tolerance=pd.Timedelta(minutes=20))
    # --- OI: 1m 값 backward asof (t시점 이미 알려진 값; oi_z는 shift(1) 계보) ---
    spine = pd.merge_asof(spine, oi, on="t", direction="backward",
                          tolerance=pd.Timedelta(minutes=5))

    # --- 선행수익(미래, 스파인=8h이므로 8h=비중첩) ---
    spine["fwd_8h"] = spine["close"].shift(-1) / spine["close"] - 1.0    # t -> t+8h
    spine["fwd_24h"] = spine["close"].shift(-3) / spine["close"] - 1.0   # t -> t+24h (8h*3)
    spine["year"] = spine["t"].dt.year
    return spine


FEATURES = {
    "fund_level": "펀딩 수준(역추세 가설: 음의 IC 기대)",
    "fund_slope": "펀딩 변화율(1차)",
    "oi_zscore_24h": "OI z점수(24h, 과열)",
    "oi_change_1h_pct": "OI 1시간 변화율(쇼크)",
    "cvd_z": "CVD z(주문흐름, 라이브계보)",
}


def ic_one(x, y):
    m = x.notna() & y.notna()
    n = int(m.sum())
    if n < 30:
        return n, np.nan, np.nan
    rho, p = stats.spearmanr(x[m], y[m])
    return n, float(rho), float(p)


def quintile_table(df, feat, ret):
    m = df[feat].notna() & df[ret].notna()
    d = df.loc[m, [feat, ret]].copy()
    if len(d) < 50:
        return None
    try:
        d["q"] = pd.qcut(d[feat].rank(method="first"), 5, labels=[1, 2, 3, 4, 5])
    except Exception:
        return None
    g = d.groupby("q", observed=True)[ret].agg(["count", "mean"])
    g["mean_bp"] = (g["mean"] * 1e4).round(1)   # bp
    return g[["count", "mean_bp"]]


def main():
    _p("=" * 78)
    _p("Funding / OI / CVD 단변량 IC 사전스크리닝 (백테 아님 · 룩어헤드 0 · 비중첩)")
    _p("=" * 78)
    panel = build_panel()
    n_total = len(panel)
    cov = panel.dropna(subset=["close"])
    _p(f"[패널] 펀딩스파인 {n_total}점 | 기간 {panel['t'].min()} ~ {panel['t'].max()}")
    _p(f"[정렬] 종가부착 {cov['close'].notna().sum()}점 | "
       f"fwd_8h유효 {panel['fwd_8h'].notna().sum()} | fwd_24h유효 {panel['fwd_24h'].notna().sum()}")
    for f in FEATURES:
        _p(f"   - {f}: 유효 {panel[f].notna().sum()}점 (NaN {panel[f].isna().sum()})")

    rows = []
    _p("\n" + "-" * 78)
    _p("[A] 전구간 IC (Spearman) — 8h(비중첩) / 24h(8h간격=3중첩, 참고) / 24h(일별 비중첩)")
    _p("-" * 78)
    _p(f"{'피처':<18}{'8h IC':>9}{'p':>9}{'n':>7} | {'24h IC':>9}{'p':>9} | {'24h비중첩 IC':>13}{'p':>9}{'n':>7}")
    nonov = panel.iloc[::3].copy()   # 24h 비중첩(매 3번째 정산=하루 간격)
    for f in FEATURES:
        n8, ic8, p8 = ic_one(panel[f], panel["fwd_8h"])
        n24, ic24, p24 = ic_one(panel[f], panel["fwd_24h"])
        nn, icn, pn = ic_one(nonov[f], nonov["fwd_24h"])
        _p(f"{f:<18}{ic8:>9.4f}{p8:>9.4f}{n8:>7} | {ic24:>9.4f}{p24:>9.4f} | {icn:>13.4f}{pn:>9.4f}{nn:>7}")
        rows.append(dict(feat=f, scope="full", ic_8h=ic8, p_8h=p8, n_8h=n8,
                         ic_24h=ic24, p_24h=p24, ic_24h_nonov=icn, p_24h_nonov=pn, n_24h_nonov=nn))

    _p("\n" + "-" * 78)
    _p("[B] 연도별 8h IC (비중첩) — 부호 안정성(§5 연도분해)")
    _p("-" * 78)
    years = sorted(panel["year"].dropna().unique())
    _p(f"{'피처':<18}" + "".join(f"{int(y):>12}" for y in years))
    for f in FEATURES:
        line = f"{f:<18}"
        for y in years:
            sub = panel[panel["year"] == y]
            _, ic, _ = ic_one(sub[f], sub["fwd_8h"])
            line += f"{ic:>12.4f}"
            rows.append(dict(feat=f, scope=f"y{int(y)}_8h", ic_8h=ic))
        _p(line)

    _p("\n" + "-" * 78)
    _p("[C] 5분위 단조성표 — 8h 선행수익 평균(bp), 1=피처최저 5=최고")
    _p("    (역추세=극단분위에서 부호반전, 추세지속=단조증가)")
    _p("-" * 78)
    for f in FEATURES:
        qt = quintile_table(panel, f, "fwd_8h")
        if qt is None:
            _p(f"  {f}: (표본부족)")
            continue
        bp = " | ".join(f"Q{int(q)}:{r.mean_bp:+.1f}" for q, r in qt.iterrows())
        _p(f"  {f:<18} {bp}")

    out = pd.DataFrame(rows)
    out_csv = os.path.join(HERE, "IC_results.csv")
    out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    panel.to_csv(os.path.join(HERE, "IC_panel.csv"), index=False, encoding="utf-8-sig")
    _p(f"\n[저장] {out_csv}")
    _p("[해석 주의] IC≠수익. 비용(14/8bp) 미적용. 유의해도 |IC|<0.03=경제적 미미. "
       "이건 스크린이지 확정아님 — 합격피처만 §15 검증엔진 백테로.")


if __name__ == "__main__":
    main()
