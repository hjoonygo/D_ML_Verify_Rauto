# -*- coding: utf-8 -*-
# [260626_02_Rauto2_Sys_Backtest2026Monthly.py] 2026년 월별 REVoi 백테 (세션 260626_02_Rauto2_Sys).
#   캡틴 질문: 라이브 최근30일 -7.8%가 대표값인지, 2026 매월로 보자.
#   데이터 = Merged_Data(2026 1~4월·검증 oi) + Dauto AWS백업미러(05-12~06-22 open_interest)
#            + 바이낸스 공개REST(OHLC 갭채움·OI hist 최근30일). ★05-01~05-11 OI갭은 ffill(표시).
#   oi_zscore = 누적OI 인과24h롤링z(검증: 앵커 1원단위 재현). 봇=REVoi MDD25(lev3/증거금75%).
#   ★무손상: 2026 1~4월은 Merged 그대로 → 검증된 앵커 계보와 동일.
import os
import sys
import json
import glob
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "04_공용엔진코드", "engines"))
from path_finder import ensure_paths  # noqa: E402
ensure_paths()
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rauto_datafeed as DF  # noqa: E402
from fib_replay_1m import load_funding  # noqa: E402
from REVoi_bot import REVoiBot  # noqa: E402
from rauto_orchestrator import RautoOrchestrator  # noqa: E402
from rauto_live import per_trade_pnl  # noqa: E402
from rauto_cex import SlipModel  # noqa: E402

MERGED = os.path.join(ROOT, "08_BTC_Data", "derived", "Merged_Data.csv")
MIRROR = r"D:\ML\Verify\08 BTC_Data\BinanceData_AWS_Mirror"
LOG = os.path.join(HERE, "260626_02_Rauto2_Sys_Backtest2026Monthly_run.log")


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def read_mirror():
    """Dauto AWS 미러 2026 → DataFrame(ohlc + open_interest), tz-naive UTC."""
    rows = []
    for fp in sorted(glob.glob(os.path.join(MIRROR, "BTCUSDT_1m_2026*.csv"))):
        try:
            df = pd.read_csv(fp, usecols=["ts_utc", "open", "high", "low", "close", "open_interest"])
            rows.append(df)
        except Exception:
            continue
    if not rows:
        return None
    m = pd.concat(rows, ignore_index=True)
    m["t"] = pd.to_datetime(m["ts_utc"], format="%Y-%m-%d %H:%M:%S")
    return m.dropna(subset=["open"]).set_index("t").sort_index()


def main():
    open(LOG, "w").close()
    _p("=" * 70)
    _p("[2026 월별 REVoi 백테] 세션 260626_02_Rauto2_Sys")
    _p("=" * 70)
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]

    # ── 1) Merged: 워밍업(2025-08~) + 2026 1~4월 (검증 oi_sum) ──
    m = pd.read_csv(MERGED, usecols=["timestamp", "open", "high", "low", "close", "oi_sum"])
    m["t"] = pd.to_datetime(m["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    m = m.dropna(subset=["open"]).set_index("t").sort_index()
    m = m[m.index >= "2025-08-01"]                      # 워밍업 충분
    merged_end = m.index.max()
    _p(f"[1] Merged 워밍업+1~4월: {m.index.min()} ~ {merged_end} ({len(m):,}행)")

    # ── 2) 확장(05-01~현재): OHLC=바이낸스klines / OI=미러+바이낸스hist, 갭 ffill ──
    kl = DF.fetch_klines_1m_range(60)                   # 최근 60일 OHLC(완전)
    bk = pd.DataFrame({"open": [k[1] for k in kl], "high": [k[2] for k in kl],
                       "low": [k[3] for k in kl], "close": [k[4] for k in kl]},
                      index=pd.to_datetime([k[0] for k in kl], unit="ms"))
    bk = bk[bk.index > merged_end].sort_index()
    ext_idx = bk.index
    _p(f"[2] 확장 OHLC(바이낸스): {ext_idx.min()} ~ {ext_idx.max()} ({len(bk):,}행)")

    # OI 소스 결합: 미러 open_interest + 바이낸스 OI hist(5m)
    oi_ext = pd.Series(np.nan, index=ext_idx)
    mir = read_mirror()
    if mir is not None:
        oi_m = mir["open_interest"].reindex(ext_idx)
        oi_ext = oi_ext.fillna(oi_m)
        _p(f"    미러 OI: {mir.index.min()} ~ {mir.index.max()}")
    try:
        oih = DF.fetch_oi_hist(30)
        oi_h = pd.Series([o[1] for o in oih], index=pd.to_datetime([o[0] for o in oih], unit="ms")).reindex(ext_idx, method="ffill")
        oi_ext = oi_ext.fillna(oi_h)
        _p(f"    바이낸스 OI hist: {len(oih)}점(최근30일)")
    except Exception as e:
        _p(f"    바이낸스 OI hist 실패: {e}")
    gap_before = int(oi_ext.isna().sum())
    oi_ext = oi_ext.ffill().bfill()                    # 05-01~05-11 갭 = 직전값 채움(표시용)
    _p(f"    OI 갭(채우기 전 결측) = {gap_before:,}분 (주로 05-01~05-11)")

    # ── 3) 결합 + oi_zscore(인과24h롤링z) ──
    ohlc = pd.concat([m[["open", "high", "low", "close"]], bk])
    ohlc = ohlc[~ohlc.index.duplicated(keep="first")].sort_index()
    raw_oi = pd.concat([m["oi_sum"], oi_ext])
    raw_oi = raw_oi[~raw_oi.index.duplicated(keep="first")].reindex(ohlc.index).ffill()
    d1m = ohlc.copy()
    d1m["oi_zscore_24h"] = DF.oi_zscore_from_series(raw_oi).values
    _p(f"[3] 결합 d1m: {d1m.index.min()} ~ {d1m.index.max()} ({len(d1m):,}행)")

    # ── 4) REVoi 구동 ──
    fund = load_funding()
    bot = REVoiBot(p)
    orch = RautoOrchestrator(bot, size_pct=75.0, lev=3.0, slip=SlipModel(0.0, 0.0))
    r = orch.run_backtest(d1m, fund)
    T = r["trades"].sort_values("et").reset_index(drop=True)
    pnl, final, mdd, nliq = per_trade_pnl(T, 75.0, 3.0)
    T = T.copy()
    T["pnl"] = pnl
    T["ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)
    T["side_i"] = T["side"].astype(int)
    _p(f"[4] 전체구간 거래 {len(T)} · 복리 {r['tot']:+.1f}% (워밍업 포함)")

    # ── 5) 2026 월별 표 ──
    _p("")
    _p("=" * 70)
    _p("★ 2026년 월별 REVoi 성과 (MDD25: 레버3·증거금75% · 슬립0·스프레드 미반영=낙관)")
    _p("=" * 70)
    _p(f"{'월':<9}{'거래':>5}{'승률':>6}{'PF':>6}{'손익비':>7}{'수익률':>9}{'롱(거래/수익)':>14}{'숏(거래/수익)':>14}  비고")
    months = [f"2026-{i:02d}" for i in range(1, 7)]
    note = {"2026-05": "OI갭(05-01~11) 일부근사", "2026-06": "~06-26(부분월)"}
    cum = 1.0
    rows2026 = []
    for ym in months:
        g = T[T["ym"] == ym]
        if len(g) == 0:
            _p(f"{ym:<9}{'0':>5}{'-':>6}{'-':>6}{'-':>7}{'0.0%':>9}{'-':>14}{'-':>14}  {note.get(ym,'')}")
            continue
        pn = g["pnl"].values
        w = pn[pn > 0]
        l = pn[pn < 0]
        wr = len(w) / len(pn) * 100
        pf = (w.sum() / abs(l.sum())) if len(l) else float("inf")
        payoff = ((w.mean()) / abs(l.mean())) if (len(w) and len(l)) else float("nan")
        ret = (np.prod(1 + pn / 100) - 1) * 100
        cum *= (1 + ret / 100)
        gl = g[g["side_i"] == 1]
        gs = g[g["side_i"] == -1]
        lret = (np.prod(1 + gl["pnl"].values / 100) - 1) * 100 if len(gl) else 0.0
        sret = (np.prod(1 + gs["pnl"].values / 100) - 1) * 100 if len(gs) else 0.0
        rows2026.append((ym, ret))
        _p(f"{ym:<9}{len(pn):>5}{wr:>5.0f}%{pf:>6.2f}{payoff:>7.2f}{ret:>+8.1f}%"
           f"{f'{len(gl)}/{lret:+.1f}%':>14}{f'{len(gs)}/{sret:+.1f}%':>14}  {note.get(ym,'')}")
    _p("-" * 70)
    tot2026 = (cum - 1) * 100
    g26 = T[T["ym"].str.startswith("2026")]
    pn26 = g26["pnl"].values
    if len(pn26):
        w26 = pn26[pn26 > 0]
        l26 = pn26[pn26 < 0]
        _p(f"{'2026합계':<9}{len(pn26):>5}{len(w26)/len(pn26)*100:>5.0f}%"
           f"{(w26.sum()/abs(l26.sum()) if len(l26) else 0):>6.2f}{'':>7}{tot2026:>+8.1f}%   (복리)")
    _p("")
    _p("[해석] · REVoi=저승률(~34%)·고손익비 전략 → 월 편차 큼. 한 달로 판단 금지(캡틴 직감 맞음).")
    _p("       · 최근 라이브 -7.8%(월 11거래)는 위 월별 분포의 약한 달에 해당하는지 대조.")
    _p("       · 1~4월=Merged 검증데이터(신뢰), 5월=OI갭 일부근사, 6월=부분월(~06-26).")
    _p("       · ★슬립0·스프레드 미반영=낙관 상한. 현실(스프1bp 등)은 더 낮음(§19/§24).")
    return True


if __name__ == "__main__":
    main()
