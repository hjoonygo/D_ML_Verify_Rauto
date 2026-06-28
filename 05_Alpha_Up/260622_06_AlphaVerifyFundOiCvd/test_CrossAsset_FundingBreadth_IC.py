# -*- coding: utf-8 -*-
# [test_CrossAsset_FundingBreadth_IC.py]
# 질문: "여러 코인 펀딩 쏠림 → BTC '방향(절대 상승/하락)'을 예측하나?" (채널1 쏠림·채널4 총레버리지)
#   ★이건 횡단면 상대알파가 아니라, '시장 전체 펀딩상태 → BTC 시계열방향' 가설의 IC 스크린.
#   ★백테 아님(PF/MDD 주장 0). 룩어헤드 0·비중첩·Spearman, §15 정신.
#
# 데이터: 바스켓 10코인 펀딩(8h, 공개REST 복구) + BTC 8h klines(가격).
#   ※알트 OI 과거는 30일만 제공 → 'OI 쏠림'은 데이터막힘(미검증 명시). 펀딩 쏠림만 검증.
#
# 신호(모두 t시점 정산값=과거, 룩어헤드 없음):
#   agg_all   = 전코인 펀딩 중앙값(시장 전체 레버리지/심리)   [채널4]
#   agg_alt   = 알트(BTC제외) 펀딩 중앙값                      [채널4, 타코인이 BTC예측]
#   agg_slope = agg_alt 직전대비 변화                          [채널4 변화]
#   breadth_pos = 알트 중 펀딩>0 비율(롱 쏠림 폭)              [채널1 쏠림]
#   breadth_hot = 알트 중 펀딩>=1e-4 비율(과열 폭)             [채널1 쏠림]
#   btc_rel   = BTC펀딩 - 알트중앙값(BTC 상대과열)             [채널3 보너스]
# 가설: 시장 과열(agg/breadth 높음) → 역추세면 BTC 음의 선행수익. 데이터가 말하게 둔다.
import os, urllib.request, urllib.parse, json
import datetime as dt
import numpy as np, pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
BASKET = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','LTCUSDT']
ALTS = [s for s in BASKET if s != 'BTCUSDT']
START = dt.datetime(2023, 6, 1, tzinfo=dt.timezone.utc)
H8 = 8 * 3600 * 1000


def _p(*a): print(*a, flush=True)


def get(path, params):
    url = 'https://fapi.binance.com' + path + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'xasset-ic'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_funding(sym, start_ms, end_ms):
    out, cur = [], start_ms
    while cur <= end_ms:
        fs = get('/fapi/v1/fundingRate', {'symbol': sym, 'startTime': cur, 'endTime': end_ms, 'limit': 1000})
        if not fs:
            break
        for x in fs:
            out.append((int(x['fundingTime']), float(x['fundingRate'])))
        cur = int(fs[-1]['fundingTime']) + 1
        if len(fs) < 1000:
            break
    return out


def fetch_klines_8h(sym, start_ms, end_ms):
    out, cur = [], start_ms
    while cur <= end_ms:
        ks = get('/fapi/v1/klines', {'symbol': sym, 'interval': '8h', 'startTime': cur, 'endTime': end_ms, 'limit': 1500})
        if not ks:
            break
        for k in ks:
            out.append((int(k[0]), float(k[1])))   # (openTime, open)
        cur = ks[-1][0] + H8
        if len(ks) < 1500:
            break
    return out


def floor8(ms):
    return (ms // H8) * H8


def build():
    end_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    start_ms = int(START.timestamp() * 1000)
    _p(f"[수집] 펀딩 {len(BASKET)}코인 + BTC 8h가격 | {START.date()} ~ now")
    fund = {}
    for s in BASKET:
        f = fetch_funding(s, start_ms, end_ms)
        d = pd.DataFrame(f, columns=['ms', s]).drop_duplicates('ms')
        d['slot'] = d['ms'].map(floor8)
        fund[s] = d.set_index('slot')[s]
        _p(f"   {s}: {len(d)} 정산")
    panel = pd.concat(fund.values(), axis=1, keys=fund.keys()).sort_index()
    # BTC 가격(8h open) = t시점 가격
    bk = fetch_klines_8h('BTCUSDT', start_ms, end_ms)
    px = pd.DataFrame(bk, columns=['slot', 'btc_open']).drop_duplicates('slot').set_index('slot')['btc_open']
    panel = panel.join(px, how='left')
    panel.index = pd.to_datetime(panel.index, unit='ms', utc=True)
    return panel


def main():
    P = build()
    alt = P[ALTS]
    sig = pd.DataFrame(index=P.index)
    sig['agg_all'] = P[BASKET].median(axis=1)
    sig['agg_alt'] = alt.median(axis=1)
    sig['agg_slope'] = sig['agg_alt'].diff()
    sig['breadth_pos'] = (alt > 0).sum(axis=1) / alt.notna().sum(axis=1)
    sig['breadth_hot'] = (alt >= 1e-4).sum(axis=1) / alt.notna().sum(axis=1)
    sig['btc_rel'] = P['BTCUSDT'] - sig['agg_alt']
    # BTC 선행수익(8h open 기준, 비중첩)
    op = P['btc_open']
    sig['fwd_8h'] = op.shift(-1) / op - 1.0
    sig['fwd_24h'] = op.shift(-3) / op - 1.0
    sig['year'] = sig.index.year
    sig = sig.dropna(subset=['fwd_8h'])

    cov = sig['agg_alt'].notna().sum()
    _p(f"\n[패널] {len(sig)} 8h슬롯 | {sig.index.min()} ~ {sig.index.max()} | 알트펀딩유효 {cov}")
    base8 = sig['fwd_8h'].mean() * 1e4
    _p(f"[베이스] BTC 8h 평균선행수익 = {base8:+.1f} bp")

    SIGS = ['agg_all', 'agg_alt', 'agg_slope', 'breadth_pos', 'breadth_hot', 'btc_rel']
    # 최근 1년 컷
    cut1y = sig.index.max() - pd.Timedelta(days=365)
    recent = sig[sig.index >= cut1y]

    def ic(x, y):
        m = x.notna() & y.notna(); n = int(m.sum())
        if n < 30: return n, np.nan, np.nan
        rho, p = stats.spearmanr(x[m], y[m]); return n, float(rho), float(p)

    _p("\n" + "-" * 82)
    _p("[A] IC (Spearman) — 전구간 8h(비중첩) / 24h / 최근1년 8h")
    _p("-" * 82)
    _p(f"{'신호':<14}{'전8h IC':>10}{'p':>8}{'n':>6} | {'전24h IC':>10}{'p':>8} | {'1년 8h IC':>11}{'p':>8}{'n':>6}")
    rows = []
    for s in SIGS:
        n8, i8, p8 = ic(sig[s], sig['fwd_8h'])
        n24, i24, p24 = ic(sig[s], sig['fwd_24h'])
        nr, ir, pr = ic(recent[s], recent['fwd_8h'])
        _p(f"{s:<14}{i8:>10.4f}{p8:>8.3f}{n8:>6} | {i24:>10.4f}{p24:>8.3f} | {ir:>11.4f}{pr:>8.3f}{nr:>6}")
        rows.append(dict(sig=s, ic8=i8, p8=p8, n8=n8, ic24=i24, p24=p24, ic1y=ir, p1y=pr))

    _p("\n" + "-" * 82)
    _p("[B] 연도별 8h IC (부호 안정성)")
    _p("-" * 82)
    years = sorted(sig['year'].unique())
    _p(f"{'신호':<14}" + "".join(f"{int(y):>11}" for y in years))
    for s in SIGS:
        line = f"{s:<14}"
        for y in years:
            sub = sig[sig['year'] == y]; _, i, _ = ic(sub[s], sub['fwd_8h']); line += f"{i:>11.4f}"
        _p(line)

    _p("\n" + "-" * 82)
    _p("[C] 5분위 단조성 — BTC 8h 선행수익(bp). Q1=신호최저 Q5=최고")
    _p("-" * 82)
    for s in SIGS:
        d = sig[[s, 'fwd_8h']].dropna()
        if len(d) < 50: continue
        try:
            d['q'] = pd.qcut(d[s].rank(method='first'), 5, labels=[1,2,3,4,5])
        except Exception:
            continue
        g = d.groupby('q', observed=True)['fwd_8h'].mean() * 1e4
        _p(f"  {s:<14} " + " | ".join(f"Q{int(q)}:{v:+.1f}" for q, v in g.items()))

    pd.DataFrame(rows).to_csv(os.path.join(HERE, "XAsset_IC_results.csv"), index=False, encoding='utf-8-sig')
    sig.to_csv(os.path.join(HERE, "XAsset_panel.csv"), encoding='utf-8-sig')
    _p(f"\n[저장] XAsset_IC_results.csv / XAsset_panel.csv")
    _p("[주의] IC≠수익·비용미적용·스크린이지확정아님. OI쏠림은 알트OI 30일한도로 데이터막힘(미검증).")


if __name__ == "__main__":
    main()
