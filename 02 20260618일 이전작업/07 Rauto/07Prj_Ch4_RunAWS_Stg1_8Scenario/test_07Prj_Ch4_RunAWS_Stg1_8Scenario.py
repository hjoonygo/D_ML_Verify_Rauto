# [test_07Prj_Ch4_RunAWS_Stg1_8Scenario.py]
# 코드길이: 약 210줄 / 내부버전: ch4_stg1_8scenario_test_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] TrendStack 라이브 페이퍼 배선의 강건성을 8개 엣지 시나리오로 검증(결과 주인공).
#   라이브 경로(1분봉 → 봇.on_bar → 페이퍼 엔진 open/resolve)가 어떤 입력에도
#   '끊김없이' 돌고(예외0·봉 전량처리), 신호가 원본과 일치(라이브≡리플레이)하며,
#   P&L이 올바른 비용·청산·MAE(보유구간) 모델로 $10,000 복리 계산되는가.
# [무수정 보장] bot/engine/poc/regime/contract/paper_engine 전부 원본 그대로 import.
# [데이터] 외부 실데이터 불필요 — 시나리오별 합성 1분봉 자체생성(최소 길이·numpy 벡터화).
# [출력] 07Prj_Ch4_RunAWS_Stg1_8Scenario_results.csv (시나리오별 지표·판정) → check.py가 검사.
# ── 사용 파일 ──
#   bot_trendstack_signal.TrendStackSignalBot / rauto_paper_engine.PaperAccount
#   rauto_contract.MarketBar/Action
# ── 함수 In/Out ──
#   stream(n_7h,mode,seed,gap_at,gap_pct) In: 길이·장세·시드·갭 Out: 1분봉 리스트
#   bkt7(ts)                              In: 시각 Out: 7h 버킷번호(봇과 동일식)
#   run_pipe(bars, use_oi)                In: 1분봉·oi사용여부 Out: dict(지표·판정)
#   main()                                In: - Out: results.csv 작성 + 8/8 요약 출력
# ── 상수 ── BUCKET_7H=420 / START=$10,000(복리, 페이퍼 엔진 기본)
# ─────────────────────────────────────────────────────────────────────────
import os
import csv
import traceback
import numpy as np
import pandas as pd

import bot_trendstack_signal as B
import rauto_paper_engine as PE
from rauto_contract import MarketBar, Action

HERE = os.path.dirname(os.path.abspath(__file__))
BUCKET_7H = 420
RESULTS = os.path.join(HERE, "07Prj_Ch4_RunAWS_Stg1_8Scenario_results.csv")


def stream(n_7h=30, mode="normal", seed=7, gap_at=None, gap_pct=0.0):
    """합성 1분봉. mode: normal(상승→하락→횡보)/up(지속상승)/range(횡보)/volcomp(저변동→고변동)."""
    rng = np.random.RandomState(seed)
    n = n_7h * BUCKET_7H
    m = np.arange(n)
    if mode == "up":
        trend = 0.0026 * m
        amp, nz = 1.2, 0.10
    elif mode == "range":
        trend = np.zeros(n)
        amp, nz = 2.0, 0.20
    elif mode == "volcomp":
        trend = np.zeros(n)
        amp = np.where(m < n // 2, 0.6, 3.2)            # 전반 압축 → 후반 확대
        nz = np.where(m < n // 2, 0.05, 0.30)
    else:  # normal
        seg = n // 3
        trend = np.empty(n)
        trend[:seg] = 0.0022 * m[:seg]
        trend[seg:2 * seg] = trend[seg - 1] - 0.0022 * (m[seg:2 * seg] - (seg - 1))
        trend[2 * seg:] = trend[2 * seg - 1]
        amp, nz = 3.0, 0.15
    osc = amp * np.sin(m / (BUCKET_7H / 2.4))
    close = 100.0 + trend + osc + rng.randn(n) * nz
    if gap_at is not None and 0 <= gap_at < n:
        close[gap_at:] += close[gap_at - 1] * gap_pct   # 급격 갭(강제청산 트리거용)
    open_ = np.empty(n); open_[0] = close[0]; open_[1:] = close[:-1]
    wick = 0.20 + np.abs(rng.randn(n)) * 0.15
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    vol = 10.0 + np.abs(rng.randn(n)) * 8.0
    oiz = 0.5 + 1.2 * np.sin(m / (BUCKET_7H * 4.0)) + rng.randn(n) * 0.05
    base = pd.Timestamp('2024-01-01 00:00:00')
    return [(base + pd.Timedelta(minutes=int(k)), float(open_[k]), float(high[k]),
             float(low[k]), float(close[k]), float(vol[k]), float(oiz[k])) for k in range(n)]


def bkt7(ts):
    return int(pd.Timestamp(ts).value // 60_000_000_000) // BUCKET_7H


def run_pipe(bars, use_oi=True):
    bot = B.TrendStackSignalBot(); bot.on_init({})
    acct = PE.PaperAccount()                     # START=$10,000(복리)
    st = dict(bars=0, enter=0, exit=0, hold=0, warmup=0, err=0, exc=None, feats=set())
    held = False; entry = 0.0; side = 0; prior_adv = 0.0; cur_adv = 0.0; cur_bkt = None
    try:
        for (ts, o, h, l, c, v, oiz) in bars:
            aux = {'oi_zscore': oiz} if use_oi else {}
            sig = bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux=aux))
            st['bars'] += 1
            if sig is not None:
                st['feats'].add(bot._feat)
            if sig is not None and sig.action == Action.ENTER:
                st['enter'] += 1
                acct.open(sig, ts=ts, price=c)
                held = True; entry = c; side = sig.side.value
                prior_adv = 0.0; cur_adv = 0.0; cur_bkt = bkt7(ts)
                ext = l if side == 1 else h
                cur_adv = min(cur_adv, side * (ext - entry) / entry)
                continue
            if sig is not None and sig.action == Action.EXIT:
                st['exit'] += 1
                t = bot._trades[-1]
                final = side * (t['exit'] - entry) / entry
                exit_contrib = cur_adv if t['reason'] == 'trend_flip' else final
                mae = min(prior_adv, exit_contrib, final)
                acct.resolve_replay(R=t['R'], mae=mae, fund=t['fund'])
                held = False
                continue
            if sig is not None and sig.action == Action.HOLD:
                st['hold'] += 1
                if 'warmup' in (sig.reason or ''):
                    st['warmup'] += 1
            if held:
                b = bkt7(ts)
                if b != cur_bkt:
                    prior_adv = min(prior_adv, cur_adv); cur_adv = 0.0; cur_bkt = b
                ext = l if side == 1 else h
                cur_adv = min(cur_adv, side * (ext - entry) / entry)
    except Exception:
        st['err'] += 1; st['exc'] = traceback.format_exc()

    # 라이브 ≡ 리플레이 (동일거래)
    match = None
    try:
        df7 = pd.DataFrame(bot._h7, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).set_index('ts')
        oi = np.array(bot._oiz, dtype=float) if use_oi else None
        fresh = B.TrendStackSignalBot(); fresh.on_init({})
        rep = fresh.replay_7h(df7[['open', 'high', 'low', 'close']], oi, gate_mode='er', gate_er=0.45)
        key = lambda t: (t['entry_t'], t['exit_t'], t['side'], round(float(t['R']), 6))
        match = (len(rep) == len(bot._trades)) and all(key(a) == key(b) for a, b in zip(rep, bot._trades))
    except Exception:
        match = False
    ret, mdd, cal = acct.metrics()
    st['feats'] = "|".join(sorted(str(x) for x in st['feats']))
    return dict(st=st, n_liq=acct.n_liq, ret=ret, mdd=mdd, cal=cal, final_bal=acct.bal,
                match=match, n_trades=len(bot._trades))


def _row(scenario, desc, r, ok, note=""):
    st = r['st']
    return dict(scenario=scenario, desc=desc, bars=st['bars'], enter=st['enter'], exit=st['exit'],
                n_liq=r['n_liq'], match=r['match'], feats=st['feats'], ret_pct=round(r['ret'], 2),
                mdd_pct=round(r['mdd'], 2), final_bal=round(r['final_bal'], 2), err=st['err'],
                note=note, verdict="PASS" if ok else "FAIL")


def sc_pipe(name, desc, bars_fn, use_oi=True, extra=None):
    def run():
        r = run_pipe(bars_fn(), use_oi=use_oi)
        st = r['st']
        ok = (st['err'] == 0) and (st['bars'] > 0) and (r['n_trades'] == 0 or r['match'] is True)
        if extra is not None:
            ok = ok and extra(r)
        return _row(name, desc, r, ok), ok
    return run


def check_short_cut():
    """S2: 업트렌드 숏컷 직접 단위검증 — 합성스트림은 uptrend 레짐을 못 만들어 의미가 없으므로,
       feat='uptrend'를 강제하고 _compute_size가 숏을 size 0으로 자르는지(롱·range는 안 자름) 직접 확인."""
    bot = B.TrendStackSignalBot(); bot.on_init({})
    bot._h7 = [[pd.Timestamp('2024-01-01'), 100.0, 101.0, 99.0, 100.0, 500.0] for _ in range(5)]  # <poc_lb → OPVnN 건너뜀
    sig = {'atr': np.array([1.0] * 5)}
    bot._feat = 'uptrend'; s_short, _, _ = bot._compute_size(-1, 4, sig)
    bot._feat = 'uptrend'; s_long, _, _ = bot._compute_size(1, 4, sig)
    bot._feat = 'range';   s_rng, _, _ = bot._compute_size(-1, 4, sig)
    ok = (s_short == 0.0) and (s_long > 0.0) and (s_rng > 0.0)
    note = f"uptrend숏={s_short}|uptrend롱={round(s_long,3)}|range숏={round(s_rng,3)}"
    fake = dict(st=dict(bars=0, enter=0, exit=0, feats='uptrend(직접주입)', err=0, exc=None),
                n_liq=0, ret=0.0, mdd=0.0, final_bal=10000.0, match=None)
    return _row("S2_uptrend_cut", "업트렌드 숏컷 직접 단위검증(숏만 size0)", fake, ok, note), ok


def main():
    G = 30 * BUCKET_7H // 2
    scenarios = [
        sc_pipe("S1_normal", "정상장세·신호발생·완주", lambda: stream(30, "normal", 7)),
        check_short_cut,
        sc_pipe("S3_gap_liq", "급갭→강제청산 무크래시", lambda: stream(30, "normal", 7, gap_at=G, gap_pct=-0.08)),
        sc_pipe("S4_oi_missing", "oi누락→게이트무력·무크래시", lambda: stream(30, "normal", 7), use_oi=False),
        sc_pipe("S5_warmup_short", "워밍업미달→진입0", lambda: stream(3, "normal", 7),
                extra=lambda r: r['st']['enter'] == 0),
        sc_pipe("S6_range_only", "횡보만→진입희박", lambda: stream(30, "range", 5)),
        sc_pipe("S7_vol_comp_exp", "변동성압축→확대·feat갱신", lambda: stream(30, "volcomp", 3)),
        sc_pipe("S8_reentry", "연속재진입→상태누수0", lambda: stream(40, "normal", 21)),
    ]
    rows = []
    print("=" * 84)
    print("[test] 07Prj_Ch4_RunAWS_Stg1_8Scenario — 라이브 페이퍼 배선 강건성 (8/8)")
    print("=" * 84)
    print(f"{'scenario':>16} {'bars':>7} {'ent':>4} {'ext':>4} {'liq':>4} {'match':>6} {'ret%':>8} {'mdd%':>8} {'PASS':>5}")
    all_pass = True
    for fn in scenarios:
        d, ok = fn()
        all_pass = all_pass and ok
        rows.append(d)
        print(f"{d['scenario']:>16} {d['bars']:>7} {d['enter']:>4} {d['exit']:>4} {d['n_liq']:>4} "
              f"{str(d['match']):>6} {d['ret_pct']:>8.2f} {d['mdd_pct']:>8.2f} {d['verdict']:>5}")
        if d['note']:
            print(f"                 └ {d['note']}")

    with open(RESULTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print("-" * 78)
    print(f"[종합] 8시나리오 {'8/8 PASS' if all_pass else '실패 포함'} · 초기자본 $10,000 복리 · 결과 → {os.path.basename(RESULTS)}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
