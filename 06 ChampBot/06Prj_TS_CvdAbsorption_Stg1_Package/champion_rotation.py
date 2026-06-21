# -*- coding: utf-8 -*-
# [champion_rotation.py] 요청3: 챔피언 TS(성급왕)↔SW(횡보) 동적교체 최적화.
#   교체는 챔피언 청산직후(포지션 빌때)만 = 전환비용 0(캡틴 확정 2026-06-20). 한 계좌가 챔피언 거래만 집행.
#   3-1: TS 연속패배 N회(3~20)면 SW로 교체(대칭: SW도 N연패면 TS복귀).
#   3-2: 장세성격 — ER(추세효율) 기준 추세=TS / 횡보=SW (진입빈도·장세 적합 계열로).
#   비교기준: 수익률(캡틴). 검증ledger 무수정(led36_king=TS, sw_patient=SW).
import os, sys
import numpy as np, pandas as pd
STG17 = r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork"
BOTS = os.path.join(STG17, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import SidewayDCA_Stg7_engine as SWENG
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = r"D:\ML\Verify\Merged_Data.csv"
SLIP = 0.0005; TS_LEV = 22.0; SW_LEV = 15.0; SW_SIZE = 26.67; SW_SHORT = SWENG.SHORT_SIZE


def load():
    ts = pd.read_csv(os.path.join(HERE, "led36_king.csv"), parse_dates=['entry_t', 'exit_t'])
    for c in ('entry_t', 'exit_t'): ts[c] = pd.to_datetime(ts[c], utc=True).dt.tz_convert(None)
    sw = pd.read_csv(os.path.join(STG17, "sw_patient.csv"), parse_dates=['entry_t', 'exit_t'])
    for c in ('entry_t', 'exit_t'): sw[c] = pd.to_datetime(sw[c], utc=True).dt.tz_convert(None)
    # ER 룩업(7h) — 장세판정
    df = pd.read_csv(DATA, usecols=lambda c: c in ('timestamp', 'open', 'high', 'low', 'close'))
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(None); df = df.set_index('timestamp')
    df7 = E.resample_tf(df, E.TF_MIN); er7 = pd.Series(E.compute_signals(df7)['er'], index=df7.index)
    # 통일 거래레코드
    T = [dict(bot='TS', t=r.entry_t, xt=r.exit_t, side=int(r.side), R=float(r.R) - (SLIP if r.reason in ('sl', 'sl_intrabar') else 0.0),
              size=float(r.size_pct), lev=TS_LEV, mae=float(r.mae), fund=float(r.fund)) for r in ts.itertuples()]
    S = [dict(bot='SW', t=r.entry_t, xt=r.exit_t, side=int(r.side), R=float(r.R),
              size=SW_SIZE * (SW_SHORT if int(r.side) == -1 else 1.0), lev=SW_LEV, mae=0.0, fund=0.0) for r in sw.itertuples()]
    return sorted(T, key=lambda x: x['t']), sorted(S, key=lambda x: x['t']), er7


def metrics(ps):
    ps = np.asarray(ps, float); eq = 10000 * np.cumprod(1 + ps); pk = np.maximum.accumulate(eq)
    mdd = ((eq / pk - 1).min()) * 100; nz = ps[np.abs(ps) > 1e-12]
    g = nz[nz > 0].sum(); b = -nz[nz < 0].sum()
    ret = (eq[-1] / 10000 - 1) * 100
    cagr = ((eq[-1] / 10000) ** (1 / 3.0) - 1) * 100
    return dict(ret=ret, mdd=mdd, cal=cagr / abs(mdd) if mdd < 0 else float('nan'),
                pf=g / b if b > 0 else float('nan'), wr=(nz > 0).mean() * 100, n=len(nz), final=eq[-1])


def apply_trade(a, tr):
    a.open(Signal(Action.ENTER, side=Side(tr['side']), size_pct=tr['size'], leverage=tr['lev']), ts=None, price=100.0)
    return float(a.resolve_replay(R=tr['R'], mae=tr['mae'], fund=tr['fund']) or 0.0)


def sim(T, S, decide):
    """이벤트구동: 챔피언 거래만 순차집행. decide(champ, consec, er, last_R)->다음 champ. 교체는 청산후(flat)."""
    a = PE.PaperAccount(10000.0); ps = []
    ti = si = 0; champ = 'TS'; consec = 0; cur_t = pd.Timestamp('2000-01-01')
    while True:
        # 현재 챔피언의 다음 거래(현재시각 이후 진입)
        if champ == 'TS':
            while ti < len(T) and T[ti]['t'] < cur_t: ti += 1
            if ti >= len(T): break
            tr = T[ti]; ti += 1
        else:
            while si < len(S) and S[si]['t'] < cur_t: si += 1
            if si >= len(S): break
            tr = S[si]; si += 1
        p = apply_trade(a, tr); ps.append(p)
        consec = consec + 1 if p < 0 else 0
        cur_t = tr['xt']
        champ = decide(champ, consec, tr)
        if champ != (tr['bot']): consec = 0   # 교체 시 연패 리셋
    return ps


def main():
    T, S, er7 = load()
    print(f"TS거래 {len(T)} / SW거래 {len(S)} | 기간 {T[0]['t'].date()}~{T[-1]['xt'].date()}")
    base = metrics(sim(T, S, lambda c, n, tr: 'TS'))   # 고정 TS(R2 챔피언)
    print(f"\n[고정 TS(R2 성급왕)] {base['ret']:+.0f}% / MDD{base['mdd']:.1f}% / Calmar{base['cal']:.1f} / PF{base['pf']:.2f} / n{base['n']}")
    base_sw = metrics(sim(T, S, lambda c, n, tr: 'SW'))
    print(f"[고정 SW] {base_sw['ret']:+.0f}% / MDD{base_sw['mdd']:.1f}% / Calmar{base_sw['cal']:.1f} / n{base_sw['n']}")

    print(f"\n=== 3-1: TS↔SW 연속패배 N회 교체 (대칭) ===")
    print(f"{'N연패':>6} {'수익':>9} {'MDD':>7} {'Calmar':>7} {'PF':>5} {'거래':>5}")
    best = None
    for N in range(3, 21):
        def decide(c, consec, tr, N=N):
            return ('SW' if c == 'TS' else 'TS') if consec >= N else c
        m = metrics(sim(T, S, decide))
        flag = '' if m['mdd'] >= -20 else ' ★MDD위반'
        print(f"{N:>6} {m['ret']:>+8.0f}% {m['mdd']:>6.1f}% {m['cal']:>7.1f} {m['pf']:>5.2f} {m['n']:>5}{flag}")
        if m['mdd'] >= -20 and (best is None or m['ret'] > best[1]['ret']): best = (N, m)

    print(f"\n=== 3-2: 장세성격(ER) 교체 — 추세(ER≥thr)=TS / 횡보=SW ===")
    print(f"{'ER임계':>7} {'수익':>9} {'MDD':>7} {'Calmar':>7} {'PF':>5} {'거래':>5}")
    for thr in (0.30, 0.35, 0.40, 0.45, 0.50):
        def decide(c, consec, tr, thr=thr):
            e = er7.asof(pd.Timestamp(tr['xt']))
            if pd.isna(e): return c
            return 'TS' if e >= thr else 'SW'
        m = metrics(sim(T, S, decide))
        flag = '' if m['mdd'] >= -20 else ' ★MDD위반'
        print(f"{thr:>7.2f} {m['ret']:>+8.0f}% {m['mdd']:>6.1f}% {m['cal']:>7.1f} {m['pf']:>5.2f} {m['n']:>5}{flag}")

    if best:
        print(f"\n[3-1 최적(MDD-20%내 최고수익)] N={best[0]}연패: {best[1]['ret']:+.0f}%/MDD{best[1]['mdd']:.1f}%/Calmar{best[1]['cal']:.1f}")
    print(f"[기준] 고정 TS {base['ret']:+.0f}%/MDD{base['mdd']:.1f}%. 교체가 이걸 수익·MDD 동반개선해야 '채택'.")


if __name__ == "__main__":
    main()
