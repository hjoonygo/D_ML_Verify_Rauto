# [logging_verify.py] 비침습 SL-타임라인 로깅 (캡틴 승인 2026-06-20).
#   §1·§15: 엔진/봇 본문 무수정. LogMixin은 로직 안 바꾸고 sl 설정시각(T_set)만 기록.
#   동치(같은 ledger) 확인 후, 인과-인지 환상율 측정: 가격이 exit_px에 'T_set 이후' 닿았나.
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import bot_trendstack_impatient_king as TBK
from bot_trendstack_signal import TrendStackSignalBot
import bt36_ledgers as BT
from rauto_contract import MarketBar, Action


class LogMixin:
    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._sl_ts = None; self._tset = []; self._n = 0
    def _flush(self):
        while self._n < len(self._trades):
            self._tset.append(self._sl_ts); self._n += 1
    def _step(self, i, arr, sig, dz, eh):
        slb = self.sl
        ev = super()._step(i, arr, sig, dz, eh)
        if (self.sl == self.sl) and (self.sl != slb):   # sl 변경됨(=설정시각 갱신)
            self._sl_ts = arr['idx'][i]
        self._flush()
        return ev
    def on_bar(self, market):
        sig = super().on_bar(market)
        self._flush()
        return sig


class LogKing(LogMixin, TBK.TrendStackImpatientKingBot): pass
class LogImp(LogMixin, BT.PinnedImpatientBot): pass
class LogPatient(LogMixin, TrendStackSignalBot): pass   # 인내(원조 §9) — 피벗대기 진입


def run_log(bot, dd):
    bot.on_init({})
    led = []; held = False; entry = 0.0; side = 0; prior = 0.0; cur = 0.0; cbkt = None; cur_size = 0.0
    bkt7 = BT.bkt7
    for ts, o, h, l, c, v, oz in dd[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi_zscore_24h']].itertuples(index=False):
        oz = float(oz) if oz == oz else float('nan')
        sig = bot.on_bar(MarketBar(ts=ts, o=o, h=h, l=l, c=c, v=v, aux={'oi_zscore': oz}))
        if sig is not None and sig.action == Action.ENTER:
            held = True; entry = c; side = sig.side.value; prior = 0.0; cur = 0.0; cbkt = bkt7(ts); cur_size = float(sig.size_pct)
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
        elif sig is not None and sig.action == Action.EXIT and held:
            t = bot._trades[-1]
            final = side * (t['exit'] - entry) / entry
            ec = cur if t['reason'] == 'trend_flip' else final
            mae = min(prior, ec, final)
            led.append(dict(entry_t=pd.Timestamp(t['entry_t']), exit_t=pd.Timestamp(ts), side=side,
                            entry_px=float(t['entry']), exit_px=float(t['exit']), R=float(t['R']),
                            size_pct=cur_size, fund=float(t.get('fund', 0.0)), mae=float(mae),
                            reason=t['reason'], year=pd.Timestamp(t['entry_t']).year))
            held = False
        elif held:
            b = bkt7(ts)
            if b != cbkt: prior = min(prior, cur); cur = 0.0; cbkt = b
            ext = l if side == 1 else h; cur = min(cur, side * (ext - entry) / entry)
    df = pd.DataFrame(led)
    df['t_set'] = [bot._tset[i] if i < len(bot._tset) else pd.NaT for i in range(len(df))]
    return df


if __name__ == "__main__":
    dd = BT.load(); print(f"data {len(dd)}")
    # 1분 OHLC (인과 환상검사용)
    TS = dd['timestamp'].values.astype('datetime64[ns]').astype(np.int64)
    LO = dd['low'].values; HI = dd['high'].values
    def i64(t): return pd.Timestamp(t).value
    for nm, mk, anchor in [("patient", LogPatient, None), ("R2_king", LogKing, "led36_king.csv"), ("R1_imp", LogImp, "led36_imp_pinned.csv")]:
        df = run_log(mk(), dd)
        if anchor:
            ak = pd.read_csv(os.path.join(HERE, anchor))
            eq = (len(df) == len(ak)) and abs(df['R'].sum() - ak['R'].sum()) < 1e-9
            print(f"\n[{nm}] {len(df)}거래 | 동치(vs {anchor}): n={len(df)}=={len(ak)} Rsum dif={abs(df['R'].sum()-ak['R'].sum()):.2e} -> {'OK' if eq else 'FAIL'}")
        else:
            print(f"\n[{nm}] {len(df)}거래 (참고 stg6 확정원장=264건) reason={df['reason'].value_counts().to_dict()}")
        df['t_set'] = pd.to_datetime(df['t_set'])
        sl = df[df['reason'].astype(str).str.contains('sl')].copy()
        n_hold = n_caus = tot = 0
        for _, r in sl.iterrows():
            sd = int(r['side']); e = r['exit_px']
            # ★창 끝: 7H청산('sl')은 exit_t가 봉시작라벨 → 체결봉 끝(+7H)까지 포함. 1분청산('sl_intrabar')은 exit_t 정확.
            ext_ns = 0 if 'intrabar' in str(r['reason']) else 420 * 60 * 1_000_000_000
            a_h = np.searchsorted(TS, i64(r['entry_t']), 'left')      # 진입라벨~청산봉끝 (관대)
            a_c = np.searchsorted(TS, i64(r['t_set']), 'left') if pd.notna(r['t_set']) else a_h  # T_set~청산봉끝 (인과)
            b = np.searchsorted(TS, i64(r['exit_t']) + ext_ns, 'right')
            if b <= a_h: continue
            tot += 1
            vis_h = (LO[a_h:b].min() <= e) if sd == -1 else (HI[a_h:b].max() >= e)
            vis_c = (LO[a_c:b].min() <= e) if (sd == -1 and b > a_c) else ((HI[a_c:b].max() >= e) if b > a_c else False)
            if not vis_h: n_hold += 1
            if not vis_c: n_caus += 1
        print(f"  환상(보유창 [진입~청산]) = {n_hold}/{tot} = {n_hold/tot*100:.1f}%")
        print(f"  환상(인과창 [T_set~청산]) = {n_caus}/{tot} = {n_caus/tot*100:.1f}%  <- 더 엄밀")
        df.to_csv(os.path.join(HERE, f"led_log_{nm}.csv"), index=False, encoding="utf-8-sig")
