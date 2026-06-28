# -*- coding: utf-8 -*-
# [E5_onchain_orthogonal.py] #2 — 직교 장기도메인(온체인) 추가. Coin Metrics 무료 API.
#   MVRV(가치/실현가 비율)·활성주소 = 파생/가격에 직교한 장기 신호. 우리 신호에 접붙여 향상·MDD축소 보나?
#   ★룩어헤드 차단: 온체인 일별 → 1일 지연 후 asof(발표지연 보수). 직교성 측정 후 IC가중 앙상블.
import os, urllib.request, urllib.parse, json
import numpy as np, pandas as pd
from scipy import stats
import alpha_verification_system as AV

HERE = os.path.dirname(os.path.abspath(__file__))


def _p(*a): print(*a, flush=True)
def zr(s): return s.rank(pct=True) - 0.5
def ic(x, y):
    m = x.notna() & y.notna(); return stats.spearmanr(x[m], y[m])[0] if m.sum() > 30 else np.nan


def cm(metric):
    base = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    out, tok = [], None
    while True:
        q = {"assets": "btc", "metrics": metric, "frequency": "1d", "start_time": "2022-06-01", "page_size": 2000}
        if tok: q["next_page_token"] = tok
        req = urllib.request.Request(base + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "e5"})
        with urllib.request.urlopen(req, timeout=25) as r: j = json.loads(r.read())
        out += j.get("data", []); tok = j.get("next_page_token")
        if not tok: break
    s = pd.Series({pd.Timestamp(d["time"]).tz_convert("UTC"): float(d[metric]) for d in out if metric in d})
    return s.sort_index()


def asof_8h(series, P, lag_days=1):
    s = series.copy(); s.index = s.index + pd.Timedelta(days=lag_days)   # 발표지연 보수
    m = pd.merge_asof(pd.DataFrame({"t": P.index}).sort_values("t"),
                      pd.DataFrame({"t": s.index, "v": s.values}).sort_values("t"),
                      on="t", direction="backward", tolerance=pd.Timedelta(days=3))
    return m.set_index("t")["v"].reindex(P.index).values


def main():
    P = AV.build_panel().sort_index()
    P["mom_24h"] = P["open"].pct_change(3)
    _p("[온체인 수집] Coin Metrics MVRV·활성주소...")
    mvrv = cm("CapMVRVCur"); aac = cm("AdrActCnt")
    _p(f"  MVRV {mvrv.index.min().date()}~{mvrv.index.max().date()} | 활성주소 {len(aac)}일")
    P["mvrv"] = asof_8h(mvrv, P)
    P["aac"] = asof_8h(aac, P)
    P["mvrv_chg"] = pd.Series(P["mvrv"], index=P.index).diff()
    P["aac_chg"] = pd.Series(P["aac"], index=P.index).pct_change(3)

    win = P.dropna(subset=["mom_24h", "oi_z", "fund_slope", "mvrv", "fwd_8h"])
    _p(f"[표본] {len(win)}")

    # ① 직교성: 온체인 vs 기존신호 상관 + 단독IC + 증분IC(기준 mom_24h)
    _p("\n① 온체인 직교성 (vs mom_24h) + 8h 예측력")
    rb = win["mom_24h"].rank()
    for c in ["mvrv", "mvrv_chg", "aac_chg"]:
        cr_m = stats.spearmanr(win[c], win["mom_24h"], nan_policy="omit")[0]
        cr_o = stats.spearmanr(win[c], win["oi_z"], nan_policy="omit")[0]
        solo = ic(win[c], win["fwd_8h"])
        rs = win[c].rank(); beta = np.polyfit(rb, rs, 1)[0]; resid = rs - beta * rb
        inc = stats.spearmanr(resid, win["fwd_8h"].rank())[0]
        tag = "직교+증분" if (abs(cr_m) < 0.4 and abs(inc) >= 0.02) else ("직교(8h약)" if abs(cr_m) < 0.4 else "중복")
        _p(f"  {c:<10} mom상관 {cr_m:+.2f} oi상관 {cr_o:+.2f} | 단독IC(8h) {solo:+.3f} | 증분IC {inc:+.3f} → {tag}")

    # ② IC가중 앙상블: 기존(mom+oi) vs +온체인
    def aligned(c):
        s = np.sign(ic(win[c], win["fwd_8h"])) or 1.0
        return zr(win[c]) * s, abs(ic(win[c], win["fwd_8h"]))
    parts = {c: aligned(c) for c in ["mom_24h", "oi_z", "mvrv", "mvrv_chg", "aac_chg"]}
    def ens(keys):
        w = sum(parts[k][1] for k in keys)
        return sum(parts[k][0] * parts[k][1] for k in keys) / (w + 1e-12)
    SIGS = [
        ("mom+oi (기존 최강)", ens(["mom_24h", "oi_z"])),
        ("◆+mvrv", ens(["mom_24h", "oi_z", "mvrv"])),
        ("◆+mvrv_chg", ens(["mom_24h", "oi_z", "mvrv_chg"])),
        ("◆+aac_chg", ens(["mom_24h", "oi_z", "aac_chg"])),
        ("◆+온체인3종", ens(["mom_24h", "oi_z", "mvrv", "mvrv_chg", "aac_chg"])),
    ]
    N = len(SIGS); fwd = win["fwd_8h"]
    _p("\n② IC가중 앙상블 — 온체인 추가시 향상되나 (검증 3단)")
    _p(f"{'앙상블':<22}{'IC':>8}{'WF안정':>7}{'net SR':>8}{'CPCV p25':>10}{'DSR':>6}{'①가능':>6}{'③배포':>6}")
    _p("-" * 74)
    for nm, s in SIGS:
        r = AV.verify_signal(nm, s, fwd, n_trials=N)
        _p(f"{nm:<22}{r['ic']:>+8.3f}{r['wf']['sign_stability']:>6.0%}{r['net_sharpe']:>8.2f}"
           f"{r['cpcv']['p25']:>10.2f}{r['dsr']['dsr']:>6.2f}{'O' if r['possibility'] else 'X':>6}{'O' if r['deployable'] else 'X':>6}")
    _p("[해석] MVRV는 장기(주~월) 신호라 8h 단독IC는 약할 수 있음 — 그래도 직교 증분/레짐 분산 효과면 앙상블·MDD에 기여.")
    _p("[다음] 향상 앙상블을 실체결 SL 시뮬(realistic_sl_sim)에 넣어 MDD 줄었는지 확인 + 매크로(FRED M2/DXY) 추가.")


if __name__ == "__main__":
    main()
