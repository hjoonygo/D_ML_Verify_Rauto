# -*- coding: utf-8 -*-
# [260626_02_Rauto2_Sys_BacktestFullMonthly.py] 전 기간(2023~2026) 월별 REVoi 대조 (세션 260626_02_Rauto2_Sys).
#   캡틴: 2026이 예외적으로 약한지 전 기간 월별로 대조. 슬립0(낙관) vs 현실(스프1bp) 병기.
#   데이터 = Merged_Data(2023-05~2026-04 검증) + Dauto미러/바이낸스(2026-05~현재). oi=누적OI 인과24h롤링z.
#   ★무손상 체크: 2023-05~2026-04 구간 복리 == 앵커 +1851.65% 대조.
import os
import sys
import json
import glob

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
LOG = os.path.join(HERE, "260626_02_Rauto2_Sys_BacktestFullMonthly_run.log")
ANCHOR = 1851.6491162901439


def _p(*a):
    print(*a, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def read_mirror():
    rows = []
    for fp in sorted(glob.glob(os.path.join(MIRROR, "BTCUSDT_1m_2026*.csv"))):
        try:
            rows.append(pd.read_csv(fp, usecols=["ts_utc", "open", "high", "low", "close", "open_interest"]))
        except Exception:
            continue
    if not rows:
        return None
    m = pd.concat(rows, ignore_index=True)
    m["t"] = pd.to_datetime(m["ts_utc"], format="%Y-%m-%d %H:%M:%S")
    return m.dropna(subset=["open"]).set_index("t").sort_index()


def monthret(pn):
    return (np.prod(1 + np.array(pn) / 100.0) - 1) * 100.0 if len(pn) else 0.0


def main():
    open(LOG, "w").close()
    _p("=" * 78)
    _p("[전 기간 월별 REVoi 대조] 2023~2026 · 슬립0(낙관) vs 현실(스프1bp)")
    _p("=" * 78)
    cfg = json.load(open(os.path.join(ROOT, "03_IDEA4Bot", "260623_07_RfRautoAlphaUp", "back2tv_rev_winners.json")))
    p = cfg["REV_MDD25_36mo"]["p"]

    m = pd.read_csv(MERGED, usecols=["timestamp", "open", "high", "low", "close", "oi_sum"])
    m["t"] = pd.to_datetime(m["timestamp"], utc=True, format="ISO8601").dt.tz_localize(None)
    m = m.dropna(subset=["open"]).set_index("t").sort_index()
    merged_end = m.index.max()

    # 2026-05~현재 확장(OHLC 바이낸스 + OI 미러/바이낸스)
    kl = DF.fetch_klines_1m_range(60)
    bk = pd.DataFrame({"open": [k[1] for k in kl], "high": [k[2] for k in kl],
                       "low": [k[3] for k in kl], "close": [k[4] for k in kl]},
                      index=pd.to_datetime([k[0] for k in kl], unit="ms"))
    bk = bk[bk.index > merged_end].sort_index()
    oi_ext = pd.Series(np.nan, index=bk.index)
    mir = read_mirror()
    if mir is not None:
        oi_ext = oi_ext.fillna(mir["open_interest"].reindex(bk.index))
    try:
        oih = DF.fetch_oi_hist(30)
        oi_h = pd.Series([o[1] for o in oih], index=pd.to_datetime([o[0] for o in oih], unit="ms")).reindex(bk.index, method="ffill")
        oi_ext = oi_ext.fillna(oi_h)
    except Exception:
        pass
    oi_ext = oi_ext.ffill().bfill()

    ohlc = pd.concat([m[["open", "high", "low", "close"]], bk])
    ohlc = ohlc[~ohlc.index.duplicated(keep="first")].sort_index()
    raw_oi = pd.concat([m["oi_sum"], oi_ext])
    raw_oi = raw_oi[~raw_oi.index.duplicated(keep="first")].reindex(ohlc.index).ffill()
    d1m = ohlc.copy()
    d1m["oi_zscore_24h"] = DF.oi_zscore_from_series(raw_oi).values
    _p(f"데이터 {d1m.index.min()} ~ {d1m.index.max()} ({len(d1m):,}행)")

    fund = load_funding()
    bot = REVoiBot(p)
    orch = RautoOrchestrator(bot, size_pct=75.0, lev=3.0, slip=SlipModel(0.0, 0.0))
    r = orch.run_backtest(d1m, fund)
    T = r["trades"].sort_values("et").reset_index(drop=True)
    pnl0, f0, _, _ = per_trade_pnl(T, 75.0, 3.0, SlipModel(0.0, 0.0))      # 슬립0
    pnlR, fR, _, _ = per_trade_pnl(T, 75.0, 3.0, SlipModel(0.0, 1.0))      # 현실 스프1bp
    T = T.copy()
    T["pnl0"] = pnl0
    T["pnlR"] = pnlR
    T["y"] = pd.to_datetime(T["et"]).dt.year
    T["mo"] = pd.to_datetime(T["et"]).dt.month
    T["ym"] = pd.to_datetime(T["et"]).dt.to_period("M").astype(str)

    # 무손상 체크: 2023-05~2026-04 구간 복리 == 앵커
    anc = T[(pd.to_datetime(T["et"]) >= "2023-05-01") & (pd.to_datetime(T["et"]) <= "2026-04-30 23:59")]
    anc_tot = monthret(anc["pnl0"].values)
    _p(f"[무손상] 2023-05~2026-04 슬립0 복리 {anc_tot:+.1f}% vs 앵커 {ANCHOR:+.1f}% (차이 {anc_tot-ANCHOR:+.1f}%p · 5~6월 확장분 제외 비교)")

    # ── 월별 그리드(슬립0) ──
    _p("")
    _p("★ 월별 수익률 그리드 (슬립0 낙관 · %) — 행=연도, 열=월")
    hdr = "연도  " + "".join(f"{mo:>7}" for mo in range(1, 13)) + f"{'연간':>9}"
    _p(hdr)
    for y in sorted(T["y"].unique()):
        cells = []
        for mo in range(1, 13):
            g = T[(T["y"] == y) & (T["mo"] == mo)]
            cells.append(f"{monthret(g['pnl0'].values):>+7.1f}" if len(g) else f"{'·':>7}")
        yr = monthret(T[T["y"] == y]["pnl0"].values)
        _p(f"{y}  " + "".join(cells) + f"{yr:>+8.1f}%")

    # ── 연도 요약(슬립0 vs 현실 + 통계) ──
    _p("")
    _p("★ 연도별 요약 (슬립0 vs 현실 스프1bp)")
    _p(f"{'연도':<6}{'거래':>5}{'승률':>6}{'PF':>6}{'슬립0 수익률':>13}{'현실 수익률':>13}")
    for y in sorted(T["y"].unique()):
        g = T[T["y"] == y]
        pn = g["pnl0"].values
        w = pn[pn > 0]
        l = pn[pn < 0]
        wr = len(w) / len(pn) * 100 if len(pn) else 0
        pf = (w.sum() / abs(l.sum())) if len(l) else 0
        _p(f"{y:<6}{len(g):>5}{wr:>5.0f}%{pf:>6.2f}{monthret(g['pnl0'].values):>+12.1f}%{monthret(g['pnlR'].values):>+12.1f}%")
    _p("-" * 50)
    _p(f"{'전체':<6}{len(T):>5}{'':>6}{'':>6}{monthret(T['pnl0'].values):>+12.1f}%{monthret(T['pnlR'].values):>+12.1f}%")

    _p("")
    _p("[해석 포인트]")
    _p(" · 2026이 전년 대비 약한가? 위 연간 슬립0/현실로 직접 대조.")
    _p(" · 현실(스프1bp)은 거래수 많을수록 더 깎임 — 약한 해일수록 현실수익이 본전/마이너스로.")
    _p(" · 2026 5월=OI 11일 갭 일부근사 · 6월=부분월(~06-26).")
    return True


if __name__ == "__main__":
    main()
