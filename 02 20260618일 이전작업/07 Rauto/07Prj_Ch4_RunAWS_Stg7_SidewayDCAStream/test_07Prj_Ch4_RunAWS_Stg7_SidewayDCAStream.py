# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg7_SidewayDCAStream.py
# 코드길이: 약 170줄 | PASS 기준(캡틴 확정 ③): ①replay = 86거래 원장 1:1 동일거래 ②mock 스트림 무크래시
# ─────────────────────────────────────────────────────────────────────────────
# [이 코드가 하는 일 — 고딩 설명]
#   A) 실데이터 리플레이: Merged_Data 1분봉 전체(약 316만봉)를 bot.on_bar로 한 봉씩 흘려
#      봇이 만든 거래를 원장(07Prj_Ch2 Stg1, 86건)과 줄단위 대조한다.
#      대조 필드: entry_t/exit_t/side/entry(±0.01)/exit(±0.01)/reason/scen/nfilled.
#      불일치는 전수 출력(가짜 PASS 금지) — 봇 헤더의 '인과성 1봉 지연 2건'의 실제 영향 측정.
#   B) mock 스트림: 합성 랜덤워크 1분봉 65일(aux 없음)을 흘려 무크래시·신호방출 확인.
#   결과 → stream_match_result.txt (check.py가 회수)
# [데이터] 상위 D:\ML\verify\Merged_Data_with_Regime_Features.csv (엔진 find_data 위임)
# ==============================================================================
import os, sys, time
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (HERE, os.path.join(HERE, "bots")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import SidewayDCA_Stg7_engine as ENG                     # noqa: E402  데이터 로드 위임(무수정)
from rauto_contract import MarketBar, Action             # noqa: E402
from bot_sidewaydca_signal import SidewayDCASignalBot    # noqa: E402

LEDGER = os.path.join(HERE, "07Prj_Ch2_SidewayDCARebuild_Stg1_ExpCutLiqSweep_ledger.csv")
OUT = os.path.join(HERE, "stream_match_result.txt")


def replay_real():
    data = ENG.find_data(); print(f"[data] {data}")
    df = ENG.load_1m(data)
    print(f"[load] {len(df):,} rows | {df.index.min()} ~ {df.index.max()} | "
          f"atr_ratio={df.attrs.get('has_atrr')} oi={df.attrs.get('has_oi')} (src={df.attrs.get('oi_source')})")
    ts = df.index.values.astype('datetime64[ns]').astype('int64')
    o = df['open'].values; h = df['high'].values; l = df['low'].values; c = df['close'].values
    v = df['volume'].values if 'volume' in df.columns else np.ones(len(df))
    ar = df['atr_ratio'].values if 'atr_ratio' in df.columns else np.full(len(df), np.nan)
    oz = df['oi_zscore_24h'].values if 'oi_zscore_24h' in df.columns else np.full(len(df), np.nan)

    bot = SidewayDCASignalBot(); bot.on_init({})
    t0 = time.time(); n = len(ts)
    for i in range(n):
        bot.on_bar(MarketBar(ts=int(ts[i]), o=float(o[i]), h=float(h[i]), l=float(l[i]),
                             c=float(c[i]), v=float(v[i]),
                             aux={'atr_ratio': float(ar[i]), 'oi_zscore_24h': float(oz[i])}))
        if (i + 1) % 500_000 == 0:
            print(f"  [replay] {i+1:,}/{n:,} ({time.time()-t0:.0f}s) trades={len(bot.trades)}")
    bot.flush_partial()
    print(f"[replay] 완료 {time.time()-t0:.0f}s | 봇거래 {len(bot.trades)}건 | 차단 {bot.blocked_n}")
    return bot


def compare(bot):
    led = pd.read_csv(LEDGER)
    bt = [{'entry_t': pd.Timestamp(t['entry_t']).strftime('%Y-%m-%d %H:%M'),
           'exit_t': pd.Timestamp(t['exit_t']).strftime('%Y-%m-%d %H:%M'),
           'side': int(t['side']), 'entry': float(t['entry']), 'exit': float(t['exit']),
           'reason': t['reason'], 'scen': t['scen'], 'nfilled': int(t['nfilled'])}
          for t in bot.trades]
    lines = [f"[A] 봇 {len(bt)}건 vs 원장 {len(led)}건"]
    n_match = 0; mism = []
    m = min(len(bt), len(led))
    for k in range(m):
        b = bt[k]; r = led.iloc[k]
        diffs = []
        if b['entry_t'] != r['entry_t']: diffs.append(f"entry_t {b['entry_t']}≠{r['entry_t']}")
        if b['exit_t'] != r['exit_t']:   diffs.append(f"exit_t {b['exit_t']}≠{r['exit_t']}")
        if b['side'] != int(r['side']):  diffs.append(f"side {b['side']}≠{r['side']}")
        if abs(b['entry'] - float(r['entry_price'])) > 0.011: diffs.append(f"entry {b['entry']:.2f}≠{r['entry_price']}")
        if abs(b['exit'] - float(r['exit_price'])) > 0.011:   diffs.append(f"exit {b['exit']:.2f}≠{r['exit_price']}")
        if b['reason'] != r['reason']:   diffs.append(f"reason {b['reason']}≠{r['reason']}")
        if b['scen'] != r['scen']:       diffs.append(f"scen {b['scen']}≠{r['scen']}")
        if b['nfilled'] != int(r['nfilled']): diffs.append(f"nfilled {b['nfilled']}≠{r['nfilled']}")
        if diffs:
            mism.append(f"  #{k+1} {b['entry_t']} | " + " / ".join(diffs))
        else:
            n_match += 1
    extra = abs(len(bt) - len(led))
    ok = (n_match == len(led)) and (len(bt) == len(led))
    lines.append(f"[A] 위치일치 {n_match}/{len(led)} | 건수차 {extra} | 필드불일치 {len(mism)}건")
    lines += mism                                  # 전수 출력(가짜 PASS 금지)

    # ── entry_t 정렬 대조(위치 밀림 보정 — 진짜 짝 기준 카테고리 통계) ──
    bmap = {(b['entry_t'], b['side']): b for b in bt}
    full = pxonly = exitdiff = 0; only_led = []; used = set()
    for _, r in led.iterrows():
        key = (r['entry_t'], int(r['side']))
        b = bmap.get(key)
        if b is None or key in used:
            only_led.append(r['entry_t']); continue
        used.add(key)
        same_core = (b['exit_t'] == r['exit_t'] and b['reason'] == r['reason']
                     and b['scen'] == r['scen'] and b['nfilled'] == int(r['nfilled'])
                     and abs(b['entry'] - float(r['entry_price'])) <= 0.011)
        px_ok = abs(b['exit'] - float(r['exit_price'])) <= 0.011
        if same_core and px_ok:
            full += 1
        elif same_core:
            pxonly += 1
        else:
            exitdiff += 1
    only_bot = [b['entry_t'] for b in bt if (b['entry_t'], b['side']) not in
                {(r['entry_t'], int(r['side'])) for _, r in led.iterrows()}]
    lines.append(f"[A-정렬] 완전일치 {full} / 출구가격만차 {pxonly} / 출구상이 {exitdiff} "
                 f"/ 원장에만 {len(only_led)} / 봇에만 {len(only_bot)}  (분모 {len(led)})")
    if only_led:
        lines.append(f"  원장에만: {only_led}")
    if only_bot:
        lines.append(f"  봇에만: {only_bot}")
    return ok, n_match, len(led), lines


def mock_stream():
    rng = np.random.default_rng(7)
    n = 65 * 1440                                  # 65일(워밍업 60봉=20일 훨씬 초과)
    ret = rng.normal(0, 0.0005, n)
    px = 60000.0 * np.cumprod(1 + ret)
    o = np.concatenate([[60000.0], px[:-1]]); c = px
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0002, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0002, n)))
    ts0 = pd.Timestamp('2026-01-01').value
    bot = SidewayDCASignalBot(); bot.on_init({})
    sig_cnt = {}
    try:
        for i in range(n):
            s = bot.on_bar(MarketBar(ts=int(ts0 + i * 60_000_000_000), o=float(o[i]),
                                     h=float(h[i]), l=float(l[i]), c=float(c[i]), v=1.0))
            if s is not None:
                sig_cnt[s.action.value] = sig_cnt.get(s.action.value, 0) + 1
        bot.flush_partial()
        return True, f"[B] mock 무크래시 | {n:,}봉 | 신호 {sig_cnt} | 거래 {len(bot.trades)}건"
    except Exception as e:
        import traceback
        return False, f"[B] mock 크래시: {e}\n{traceback.format_exc()}"


def main():
    print("[TEST Stg7] A=실데이터 리플레이 원장대조 / B=mock 무크래시")
    bot = replay_real()
    ok_a, n_match, n_led, lines_a = compare(bot)
    ok_b, line_b = mock_stream()
    n_pass = int(ok_a) + int(ok_b)
    verdict = (f"VERDICT {n_pass}/2 PASS | A: 원장일치 {n_match}/{n_led}"
               f"{'(1:1)' if ok_a else '(불일치 — 본문 전수기록)'} | B: mock {'OK' if ok_b else 'CRASH'}")
    body = [verdict] + lines_a + [line_b]
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")
    for x in body[:40]:
        print(x)
    print(f"[save] {OUT}")


if __name__ == "__main__":
    main()
