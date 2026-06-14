# -*- coding: utf-8 -*-
# [파일명] test_07Prj_Ch4_RunAWS_Stg17_ImpatientFork.py
# 코드길이: 약 270줄 | 내부버전: ch4_stg17_impatient_fork_v1 (Stg14 완전체 1:1 + TS봇만 인내심없는 분기)
#   ★Stg14 대비 유일 차이 = TS 신호봇 인스턴스를 TrendStackImpatientBot(피벗대기 제거)로 교체(98·212줄).
#   엔진·OPVnN·OI계보·ATR·페이퍼엔진·배분레이어·SW봇·동치검사 전부 Stg14와 동일. 출력은 본 폴더로 격리.
# ─────────────────────────────────────────────────────────────────────────────
# [목적 — Stg14 단계점화: v1 예열(oi_z=NaN) PASS → v2 완전체(OI축) 전환]
#   라이브 페이퍼 전체 배선(Dauto 1m CSV → Stg13 어댑터(REPAIRED 계보 oi_zscore_24h)
#   → TS BotPlugin + SW 인과봇 → 배분레이어 k=0.77 + SW ER>=0.40×0.5 → 슬롯계좌):
#   ① 예외 0·전봉 처리 ② TS 라이브≡리플레이 동치(oi 포함) ③ 일일 스코어카드
#   ④ ER댐핑 모니터링(댐핑/무댐핑 가상 P&L 병기) ⑤ oi_z 커버리지·뭉툭화(blunt) 비율.
# [완전체-OI축 잔여 근사 — 공식 1주에서 정밀화]
#   - atr_ratio aux는 여전히 미공급(별도 공급원 미구축) → SW 정밀필터는 OI축만 가동
#   - SW R = side×(exit-avg)/avg - 0.0014(왕복비용), 펀딩 0 (TS는 봇 원장 R·fund 그대로)
#   - 슬롯계좌 2개(봇당 $10,000) — Stg6식 단일계좌 합성지표는 공식검증에서
# [근간] C:\BinanceData\BTCUSDT_1m_*.csv + bots\(§8 5종 + SW봇 f758ef6d + oi_zscore_adapter)
# [Out] stg14_result.txt / paper_ledger.csv / scorecard_daily.csv
# ==============================================================================
import os, sys, glob, traceback
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path:
    sys.path.insert(0, BOTS)
import bot_trendstack_signal as TB                  # §8 040da0d2 (부모 — 무수정)
import bot_trendstack_impatient as TBI              # 분기: TrendStackImpatientBot(_step만 오버라이드)
import bot_sidewaydca_signal as SB                  # f758ef6d (Stg8 인증판, 분기에서 무변경)
import trendstack_signal_engine as TE               # §8 c9d784bf (ER 산출)
import rauto_paper_engine as PE                     # §8 f3ff3e65 (COST 27줄 0.0014)
from rauto_contract import MarketBar, Action        # §8 40b974ac
from oi_zscore_adapter import build_aux             # Stg13 확정(REPAIRED 계보)
from atr_ratio_adapter import build_aux as build_atr_aux, N_WARM_4H_DEFAULT  # Stg15 확정

DAUTO_DIR = r"C:\BinanceData"
K_ALLOC = 0.77                                      # §9 확정 배분
ER_TREND = 0.40
W_DAMP = 0.5
SW_COST = 0.0014                                    # 예열 근사: SW 왕복비용
BUCKET_7H = 420
OUT_TXT = os.path.join(HERE, "stg14_result.txt")
OUT_LED = os.path.join(HERE, "paper_ledger.csv")
OUT_SCD = os.path.join(HERE, "scorecard_daily.csv")


def load_stream():
    files = sorted(glob.glob(os.path.join(DAUTO_DIR, "BTCUSDT_1m_*.csv")))
    if not files:
        raise FileNotFoundError(f"Dauto CSV 없음: {DAUTO_DIR}")
    dd = pd.concat([pd.read_csv(f, usecols=['ts_utc', 'open', 'high', 'low', 'close', 'volume'])
                    for f in files])
    dd['ts_utc'] = pd.to_datetime(dd['ts_utc'])
    dd = dd.drop_duplicates('ts_utc').sort_values('ts_utc').reset_index(drop=True)
    n0 = len(dd)
    dd = dd.dropna(subset=['open', 'high', 'low', 'close'])
    return dd, n0 - len(dd)


def er_now(ts_bot):
    """SW 진입시점 ER — TS봇 7h 마감히스토리로 TE.compute_signals (Stg12B와 동일 산식)."""
    try:
        if len(ts_bot._h7) < 25:
            return np.nan
        df7 = pd.DataFrame(ts_bot._h7, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).set_index('ts')
        sig = TE.compute_signals(df7[['open', 'high', 'low', 'close']])
        return float(np.asarray(sig['er'], float)[-1])
    except Exception:
        return np.nan


def bkt7(ts):
    return int(pd.Timestamp(ts).value // 60_000_000_000) // BUCKET_7H


def main():
    lines = []
    def log(s):
        print(s); lines.append(s)

    dd, drop_n = load_stream()
    aux_df = build_aux()                                    # REPAIRED 계보 z + oi_blunt
    aux_df['ts_utc'] = pd.to_datetime(aux_df['ts_utc'])
    dd = dd.merge(aux_df[['ts_utc', 'oi_zscore_24h', 'oi_blunt']], on='ts_utc', how='left')
    atr_df = build_atr_aux()                                # Stg15 확정(원본 c3ace85e 코드패스)
    atr_df['ts_utc'] = pd.to_datetime(atr_df['ts_utc'])
    dd = dd.merge(atr_df, on='ts_utc', how='left')
    # 보수 정책: atr_warm(수렴 전 N=137 4H봉) 구간은 NaN 공급 → 정밀필터 통과 관성(백테 워밍업과 동일)
    dd.loc[dd['atr_warm'] == 1, 'atr_ratio'] = np.nan
    n_zfin = int(np.isfinite(dd['oi_zscore_24h']).sum())
    n_afin = int(np.isfinite(dd['atr_ratio']).sum())
    log(f"[입력] Dauto 1m {len(dd)}행({dd.ts_utc.iloc[0]}~{dd.ts_utc.iloc[-1]}) | OHLC결측 제외 {drop_n}행")
    log(f"[aux] Stg13 oi_z: 유한 {n_zfin}({n_zfin/len(dd)*100:.2f}%) blunt {int((dd['oi_blunt']==1).sum())} "
        f"| Stg15 atr_ratio: 유한(수렴후) {n_afin}({n_afin/len(dd)*100:.2f}%) warm제외 N={N_WARM_4H_DEFAULT}4H봉")
    log(f"[배선] TS+SW BotPlugin → 배분레이어 k={K_ALLOC}·SW ER>={ER_TREND}×{W_DAMP} → 슬롯계좌 $10k×2 | 완전체(OI+ATR축) 모드")

    ts_bot = TBI.TrendStackImpatientBot(); ts_bot.on_init({})   # ★분기: 인내심없는 TS
    sw_bot = SB.SidewayDCASignalBot(); sw_bot.on_init({})
    acct_ts = PE.PaperAccount(); acct_sw = PE.PaperAccount()

    ledger = []
    daily = {}
    def day_row(d):
        return daily.setdefault(d, dict(date=str(d), bars_in=0, gap_n=0, sig_ts_n=0, sig_sw_n=0,
                                        trade_n=0, pnl_d_ts=0.0, pnl_d_sw=0.0, bal_ts=acct_ts.bal,
                                        bal_sw=acct_sw.bal, oi_z_cover=0.0, er_damp_n=0,
                                        pnl_damped=0.0, pnl_undamped=0.0, slip_p50_bp='', equiv_chk=''))

    # TS MAE 추적 상태(Stg1 run_pipe 1:1)
    ts_held = False; ts_entry = 0.0; ts_side = 0
    ts_prior_adv = 0.0; ts_cur_adv = 0.0; ts_cur_bkt = None
    # SW MAE·댐핑 상태
    sw_mae = 0.0; sw_damped = False; sw_er = np.nan
    err = 0; exc_txt = ""
    prev_ts = None

    try:
        prev_blocked = 0
        for ts, o, h, l, c, v, oz, blunt, ar, aw in dd.itertuples(index=False):
            d = ts.date(); row = day_row(d)
            row['bars_in'] += 1
            if prev_ts is not None and (ts - prev_ts) > pd.Timedelta(minutes=1):
                row['gap_n'] += 1
            prev_ts = ts
            oz = float(oz) if oz == oz else float('nan')                # NaN 안전
            ar = float(ar) if ar == ar else float('nan')
            if np.isfinite(oz):
                row['oi_z_fin_n'] = row.get('oi_z_fin_n', 0) + 1
            if blunt == 1:
                row['oi_blunt_n'] = row.get('oi_blunt_n', 0) + 1
            if np.isfinite(ar):
                row['atr_fin_n'] = row.get('atr_fin_n', 0) + 1
            mb_ts = MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz})
            mb_sw = MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v,
                              aux={'oi_zscore_24h': oz, 'atr_ratio': ar})

            # ── TS 슬롯 ──
            sig = ts_bot.on_bar(mb_ts)
            if sig is not None and sig.action == Action.ENTER:
                row['sig_ts_n'] += 1
                sig.size_pct = sig.size_pct * K_ALLOC                  # 배분레이어
                acct_ts.open(sig, ts=ts, price=c)
                ts_held = True; ts_entry = c; ts_side = sig.side.value
                ts_prior_adv = 0.0; ts_cur_adv = 0.0; ts_cur_bkt = bkt7(ts)
                ext = l if ts_side == 1 else h
                ts_cur_adv = min(ts_cur_adv, ts_side * (ext - ts_entry) / ts_entry)
            elif sig is not None and sig.action == Action.EXIT and ts_held:
                row['sig_ts_n'] += 1
                t = ts_bot._trades[-1]
                final = ts_side * (t['exit'] - ts_entry) / ts_entry
                exit_contrib = ts_cur_adv if t['reason'] == 'trend_flip' else final
                mae = min(ts_prior_adv, exit_contrib, final)
                bal0 = acct_ts.bal
                p = acct_ts.resolve_replay(R=t['R'], mae=mae, fund=t['fund'])
                ts_held = False
                row['trade_n'] += 1; row['pnl_d_ts'] += (acct_ts.bal / bal0 - 1.0)
                ledger.append(dict(bot='TS', entry_t=t['entry_t'], exit_t=ts, side=ts_side,
                                   R=round(float(t['R']), 6), mae=round(mae, 6), p=round(p or 0.0, 6),
                                   bal=round(acct_ts.bal, 2), reason=t['reason'], damped='', er_entry=''))
            elif ts_held:
                b = bkt7(ts)
                if b != ts_cur_bkt:
                    ts_prior_adv = min(ts_prior_adv, ts_cur_adv); ts_cur_adv = 0.0; ts_cur_bkt = b
                ext = l if ts_side == 1 else h
                ts_cur_adv = min(ts_cur_adv, ts_side * (ext - ts_entry) / ts_entry)

            # ── SW 슬롯 ──
            sigw = sw_bot.on_bar(mb_sw)
            if sigw is not None and sigw.action == Action.ENTER:
                row['sig_sw_n'] += 1
                sw_er = er_now(ts_bot)
                sw_damped = (not np.isnan(sw_er)) and (sw_er >= ER_TREND)
                w = W_DAMP if sw_damped else 1.0
                if sw_damped:
                    row['er_damp_n'] += 1
                sigw.size_pct = sigw.size_pct * K_ALLOC * w            # 배분레이어+댐핑
                acct_sw.open(sigw, ts=ts, price=c)
                sw_mae = 0.0
            elif sigw is not None and sigw.action == Action.EXIT and acct_sw.pos is not None:
                row['sig_sw_n'] += 1
                t = sw_bot.trades[-1]
                rg = t['side'] * (t['exit'] - t['entry']) / t['entry']
                R = rg - SW_COST                                       # 예열 근사(주석 헤더)
                bal0 = acct_sw.bal
                exp_used = acct_sw.pos['exposure']
                p = acct_sw.resolve_replay(R=R, mae=sw_mae, fund=0.0)
                row['trade_n'] += 1; row['pnl_d_sw'] += (acct_sw.bal / bal0 - 1.0)
                p_damped = p or 0.0
                p_undamp = (p_damped / W_DAMP) if sw_damped and exp_used > 0 else p_damped
                if sw_damped:
                    row['pnl_damped'] += p_damped; row['pnl_undamped'] += p_undamp
                ledger.append(dict(bot='SW', entry_t=t['entry_t'], exit_t=ts, side=t['side'],
                                   R=round(R, 6), mae=round(sw_mae, 6), p=round(p_damped, 6),
                                   bal=round(acct_sw.bal, 2), reason=t['reason'],
                                   damped=int(sw_damped), er_entry=round(sw_er, 4) if not np.isnan(sw_er) else ''))
            if sw_bot.pos != 0 and not np.isnan(sw_bot.avg):
                ext = l if sw_bot.side == 1 else h
                sw_mae = min(sw_mae, sw_bot.side * (ext - sw_bot.avg) / sw_bot.avg)
            if sw_bot.blocked_n != prev_blocked:                        # 정밀/OI필터 차단 일일집계
                row['flt_blk_n'] = row.get('flt_blk_n', 0) + (sw_bot.blocked_n - prev_blocked)
                prev_blocked = sw_bot.blocked_n

            row['bal_ts'] = round(acct_ts.bal, 2); row['bal_sw'] = round(acct_sw.bal, 2)
    except Exception:
        err += 1; exc_txt = traceback.format_exc()

    # TS 라이브≡리플레이 동치(Stg1 1:1, oi=None)
    match = None
    try:
        df7 = pd.DataFrame(ts_bot._h7, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).set_index('ts')
        fresh = TBI.TrendStackImpatientBot(); fresh.on_init({})   # ★분기 동치검사도 인내심없는 봇
        oi_arr = np.array(ts_bot._oiz, dtype=float)                    # 완전체: oi 포함 동치
        rep = fresh.replay_7h(df7[['open', 'high', 'low', 'close']], oi_arr, gate_mode='er', gate_er=0.45)
        key = lambda t: (t['entry_t'], t['exit_t'], t['side'], round(float(t['R']), 6))
        match = (len(rep) == len(ts_bot._trades)) and all(key(a) == key(b) for a, b in zip(rep, ts_bot._trades))
    except Exception:
        match = False

    for r in daily.values():
        r['equiv_chk'] = 'O' if match else 'X'
        r['mdd_ts'] = round(acct_ts.mdd * 100, 2); r['mdd_sw'] = round(acct_sw.mdd * 100, 2)
        r['oi_z_cover'] = round(r.pop('oi_z_fin_n', 0) / max(r['bars_in'], 1) * 100, 2)
        r['oi_blunt_pct'] = round(r.pop('oi_blunt_n', 0) / max(r['bars_in'], 1) * 100, 2)
        r['atr_cover'] = round(r.pop('atr_fin_n', 0) / max(r['bars_in'], 1) * 100, 2)
        r['flt_blk_n'] = r.get('flt_blk_n', 0)
    scd = pd.DataFrame(sorted(daily.values(), key=lambda r: r['date']))
    scd.to_csv(OUT_SCD, index=False, encoding='utf-8-sig')
    pd.DataFrame(ledger).to_csv(OUT_LED, index=False, encoding='utf-8-sig')

    n7 = len(ts_bot._h7); n8 = len(sw_bot.c8)
    rt, mt, _ = acct_ts.metrics(); rs, ms, _ = acct_sw.metrics()
    log(f"\n[처리] 1m {sum(r['bars_in'] for r in daily.values())}행 | 갭 {sum(r['gap_n'] for r in daily.values())}건 "
        f"| 7h봉 {n7} | 8h봉 {n8} | 예외 {err}")
    log(f"[워밍업] TS 필요60×7h={'충족' if n7 >= 60 else '미충족'}({n7}) | SW 필요60×8h={'충족' if n8 >= 60 else '미충족'}({n8})")
    log(f"[거래] TS {len(ts_bot._trades)}건(잔고 ${acct_ts.bal:,.2f} {rt:+.2f}%/MDD {mt:.2f}%) | "
        f"SW {len(sw_bot.trades)}건(잔고 ${acct_sw.bal:,.2f} {rs:+.2f}%/MDD {ms:.2f}%) | SW차단 {sw_bot.blocked_n}")
    log(f"[동치] TS 라이브≡리플레이: {match}")
    log(f"[댐핑] ER>={ER_TREND} SW진입 {sum(r['er_damp_n'] for r in daily.values())}건 "
        f"(댐핑P&L합 {sum(r['pnl_damped'] for r in daily.values()):+.4f} / 무댐핑가상 {sum(r['pnl_undamped'] for r in daily.values()):+.4f})")
    if err:
        log("\n[예외 전문]\n" + exc_txt)

    ok = (err == 0) and (match in (True, None)) and os.path.exists(OUT_SCD)
    verdict = (f"VERDICT Stg17 ImpatientFork(인내심없는 TS+동일 SW) | {'PASS' if ok else 'FAIL'} — 예외{err}·동치(oi포함){match}·"
               f"TS{len(ts_bot._trades)}/SW{len(sw_bot.trades)}거래·차단{sw_bot.blocked_n}·스코어카드 {len(scd)}일·"
               f"z커버 {n_zfin/len(dd)*100:.1f}%·atr커버 {n_afin/len(dd)*100:.1f}% | "
               f"k{K_ALLOC}+ER댐핑+Stg13/15 aux | {'공식 1주 개시 준비 완료(AWS live 12h+atr 23일 워밍업 후)' if ok else '보류'}")
    log("\n" + verdict)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
