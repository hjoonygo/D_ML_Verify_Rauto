# [exitladder_research.py] 적응형 청산 사다리 연구 (캡틴 지시 2026-06-20: 전부진행).
#   §1 준수: 검증엔진/봇 본문 무수정. king봇 서브클래스로 _step의 'ratio'만 적응형 훅으로 교체.
#   E0=baseline(부모 fib 그대로) → led36_king과 1:1 동치여야 정상(§15.2 앵커).
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); BOTS = os.path.join(HERE, "bots")
if BOTS not in sys.path: sys.path.insert(0, BOTS)
import trendstack_signal_engine as E
import bot_trendstack_impatient_king as TBK
from bot_trendstack_signal import BUCKET_7H
import bt36_ledgers as BT
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

GAPLOG = []   # 청산마다: sl이 체결봉 범위 밖이면 유리체결분(bp), 안이면 0


class ExitLadderBot(TBK.TrendStackImpatientKingBot):
    """king(1m SL가드+쿨다운) 그대로 + impatient _step의 ratio만 정책별 적응형."""
    POLICY = "E0"
    REALISTIC = False
    STRICT = False   # 걸침검사: sl이 봉범위 안(l<=sl<=h)일 때만 체결(가격이 실제 닿음)
    PT_X = 0.0       # 1분 실시간 수익트레일: 고점 대비 PT_X% 되돌리면 청산(고점*(1-x) 롱)

    def on_init(self, ctx=None):
        super().on_init(ctx)
        self._pl_hist = []; self._ph_hist = []; self._mfe_px = np.nan

    # ── king._step 복제(쿨다운 래퍼) — super()._step 대신 내 포크 호출 ──
    def _step(self, i, arr, sig, dz_oi, eh):
        ev = self._step_forked(i, arr, sig, dz_oi, eh)
        if ev is not None and ev[0] == 'ENTER' and self._cooldown_bucket is not None:
            bucket = self._bucket(arr['idx'][i], BUCKET_7H)
            if bucket == self._cooldown_bucket:
                self.pos = 0; self.entry_price = np.nan; self.entry_i = -1
                self.sl = np.nan; self.pb = 0
                return None
        return ev

    # ── impatient._step 1:1 복제 + ratio만 self._calc_ratio() 훅 ──
    def _step_forked(self, i, arr, sig, dz_oi, eh):
        if i < (E.LEFT + E.RIGHT + 1):
            return None
        high, low, close, open_, idx = arr['h'], arr['l'], arr['c'], arr['o'], arr['idx']
        Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']

        def n_fund(a, b):
            return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: self.lastPH = ph_conf[i][1]; self._ph_hist.append(ph_conf[i][1])
        if new_pl: self.lastPL = pl_conf[i][1]; self._pl_hist.append(pl_conf[i][1])

        if self.pos != 0:
            if (self.pos == 1 and Trend[i] == -1) or (self.pos == -1 and Trend[i] == 1):
                px = close[i]; R = self.pos * (px - self.entry_price) / self.entry_price * E.LEVERAGE
                fp = E.FUND_8H * n_fund(self.entry_i, i); R = R - E.COST - fp
                self._trades.append({'entry_t': idx[self.entry_i], 'exit_t': idx[i], 'side': self.pos,
                                     'entry': self.entry_price, 'exit': px, 'R': R, 'reason': 'trend_flip',
                                     'bars': i - self.entry_i, 'fund': fp, 'year': idx[i].year})
                self.pos = 0; self.sl = np.nan; self.pb = 0
                return 'EXIT', 'trend_flip'
            if i > self.entry_i and not np.isnan(self.sl):
                o_, h_, l_, c_ = open_[i], high[i], low[i], close[i]
                ticks = (o_, h_, l_, c_) if c_ < o_ else (o_, l_, h_, c_)
                hit = False
                if self.STRICT:
                    hit = (l_ <= self.sl <= h_)   # 걸침: sl이 봉범위 안에서만
                else:
                    for px in ticks:
                        if self.pos == 1 and px <= self.sl: hit = True; break
                        if self.pos == -1 and px >= self.sl: hit = True; break
                if hit:
                    R = self.pos * (self.sl - self.entry_price) / self.entry_price * E.LEVERAGE
                    fp = E.FUND_8H * n_fund(self.entry_i, i); R = R - E.COST - fp
                    self._trades.append({'entry_t': idx[self.entry_i], 'exit_t': idx[i], 'side': self.pos,
                                         'entry': self.entry_price, 'exit': self.sl, 'R': R, 'reason': 'sl',
                                         'bars': i - self.entry_i, 'fund': fp, 'year': idx[i].year})
                    self.pos = 0; self.sl = np.nan; self.pb = 0
                    return 'EXIT', 'sl'

        # ── 피보 트레일: ratio만 적응형 훅 (스톱 위치는 부모와 동일) ──
        if self.pos == 1 and new_pl:
            self.pb += 1; ratio = self._calc_ratio(i, 1, sig, ph_conf, pl_conf)
            if not np.isnan(self.lastPH):
                cand = self.lastPH - ratio * (self.lastPH - pl_conf[i][1])
                self.sl = cand if np.isnan(self.sl) else max(self.sl, cand)
        if self.pos == -1 and new_ph:
            self.pb += 1; ratio = self._calc_ratio(i, -1, sig, ph_conf, pl_conf)
            if not np.isnan(self.lastPL):
                cand = self.lastPL + ratio * (ph_conf[i][1] - self.lastPL)
                self.sl = cand if np.isnan(self.sl) else min(self.sl, cand)

        if self.pos == 0:
            le = Trend[i] == 1 and not np.isnan(self.lastPH) and not np.isnan(self.lastPL)
            se = Trend[i] == -1 and not np.isnan(self.lastPH) and not np.isnan(self.lastPL)
            if se and E.short_blocked_combo(sig, i, self.short_adx, self.short_mode, self.short_atrmult):
                se = False
            if dz_oi is not None:
                z = dz_oi[i]
                if not np.isnan(z) and (self.dz_lo <= z < self.dz_hi):
                    if self.gate_mode == 'none': is_trend = True
                    elif self.gate_mode == 'adx': is_trend = sig['adx'][i] >= self.gate_adx
                    elif self.gate_mode == 'er': is_trend = sig['er'][i] >= self.gate_er
                    else: is_trend = True
                    if is_trend: le = False; se = False
            if le or se:
                d = 1 if le else -1
                ep = close[i]
                self.pos = d; self.entry_price = ep; self.entry_i = i; self.pb = 0
                self.sl = ep * (1 - d * E.SL_PCT / 100)
                self._pl_hist = []; self._ph_hist = []; self._mfe_px = np.nan   # 진입마다 리셋
                return 'ENTER', d
        return None

    # ── king on_bar 복제 + 체결가 측정/현실화: 숏청산 sl<봉저점 / 롱청산 sl>봉고점 = 비현실 유리체결 ──
    def on_bar(self, market):
        if self.pos != 0 and not np.isnan(self.sl) and self._entry_bucket is not None:
            cur_b7 = self._bucket(market.ts, BUCKET_7H)
            if self.STRICT:
                touched = (market.l <= self.sl <= market.h)   # 걸침: 가격이 sl에 실제 닿음
            else:
                touched = (self.pos == 1 and market.l <= self.sl) or (self.pos == -1 and market.h >= self.sl)
            if cur_b7 >= self._entry_bucket and touched:
                # 측정: sl이 체결봉 범위 밖이면 유리체결분(bp) 기록
                if self.pos == -1 and self.sl < market.l:
                    GAPLOG.append((market.l - self.sl) / self.sl * 1e4)
                elif self.pos == 1 and self.sl > market.h:
                    GAPLOG.append((self.sl - market.h) / self.sl * 1e4)
                else:
                    GAPLOG.append(0.0)
                fill = self.sl
                if self.REALISTIC:
                    fill = max(self.sl, market.l) if self.pos == -1 else min(self.sl, market.h)
                ms = int(pd.Timestamp(market.ts).value // 60_000_000_000)
                held8 = max(0, (ms - self._entry_ms) // 480) if self._entry_ms else 0
                fp = E.FUND_8H * held8
                R = self.pos * (fill - self.entry_price) / self.entry_price * E.LEVERAGE - E.COST - fp
                et = self._h7[self.entry_i][0] if (0 <= self.entry_i < len(self._h7)) else pd.Timestamp(market.ts)
                self._trades.append({'entry_t': et, 'exit_t': pd.Timestamp(market.ts), 'side': self.pos,
                                     'entry': self.entry_price, 'exit': float(fill), 'R': R,
                                     'reason': 'sl_intrabar', 'bars': 0, 'fund': fp,
                                     'year': pd.Timestamp(market.ts).year})
                self.pos = 0; self.sl = np.nan; self.pb = 0; self._entry_bucket = None
                self._cooldown_bucket = cur_b7
                return Signal(Action.EXIT, side=Side.FLAT, reason='sl_intrabar')
        # ── 1분 실시간 수익트레일(인과: 이 봉 고저로 다음 봉용 sl 갱신) ──
        if self.pos != 0 and self.PT_X > 0 and not np.isnan(self.sl):
            if self.pos == 1:
                self._mfe_px = market.h if np.isnan(self._mfe_px) else max(self._mfe_px, market.h)
                self.sl = max(self.sl, self._mfe_px * (1 - self.PT_X))
            else:
                self._mfe_px = market.l if np.isnan(self._mfe_px) else min(self._mfe_px, market.l)
                self.sl = min(self.sl, self._mfe_px * (1 + self.PT_X))
        sig = super(TBK.TrendStackImpatientKingBot, self).on_bar(market)
        if sig is not None and sig.action == Action.ENTER:
            self._entry_bucket = self._bucket(market.ts, BUCKET_7H)
            self._entry_ms = int(pd.Timestamp(market.ts).value // 60_000_000_000)
        return sig

    # ── ratio 정책 ── 기본 fib[pb] (E0=부모와 동일). 낮은 ratio=타이트=수익 더 확보.
    def _baseline_ratio(self):
        f = self.fib
        return f[0] if self.pb == 1 else f[1] if self.pb == 2 else f[2]

    def _calc_ratio(self, i, side, sig, ph_conf, pl_conf):
        pol = self.POLICY[:-1] if self.POLICY.endswith("r") else self.POLICY
        base = self._baseline_ratio()
        if pol == "E0":
            return base
        if pol == "E1":                      # 항상 타이트 (확보 80/70/70%)
            return (0.2, 0.3, 0.3)[min(self.pb - 1, 2)]
        if pol == "E2":                      # 바닥/천정구조 감지 시만 타이트(확보 0.75)
            if side == -1:                   # 숏: 피벗 저점이 상승=바닥구조
                h = self._pl_hist
                if len(h) >= 2 and h[-1] > h[-2]:
                    return min(base, 0.25)
            else:                            # 롱: 피벗 고점이 하락=천정구조
                h = self._ph_hist
                if len(h) >= 2 and h[-1] < h[-2]:
                    return min(base, 0.25)
            return base
        return base


import re
def make(policy):
    def _f():
        b = ExitLadderBot()
        b.STRICT = policy.endswith("s"); b.REALISTIC = policy.endswith("r")
        mm = re.match(r"PT(\d+)", policy)
        if mm:
            b.PT_X = int(mm.group(1)) / 100.0; b.POLICY = "E0"   # 피벗트레일=기본, 수익트레일이 잠금
        else:
            b.POLICY = policy.rstrip("rs")
        return b
    return _f


def metrics(led, k=1.0):
    def _run(sub):
        a = PE.PaperAccount(10000.0)
        for _, r in sub.iterrows():
            sd = int(r['side']); size = float(r['size_pct']) * k
            R = float(r['R']) - (0.0005 if r['reason'] in ('sl', 'sl_intrabar') else 0.0)
            a.open(Signal(Action.ENTER, side=Side(sd), size_pct=size, leverage=22.0), ts=None, price=100.0)
            a.resolve_replay(R=R, mae=float(r['mae']) if size > 0 else 0.0, fund=float(r['fund']))
        return a.metrics()
    ret, mdd, _ = _run(led)
    lr = _run(led[led['side'] == 1])[0]; sr = _run(led[led['side'] == -1])[0]
    return dict(n=len(led), ret=ret, mdd=mdd, long=lr, short=sr,
                reasons=led['reason'].value_counts().to_dict())


if __name__ == "__main__":
    import sys as _s
    pols = _s.argv[1:] or ["E1", "E2"]
    dd = BT.load(); print(f"data {len(dd)} {dd.timestamp.iloc[0]}~{dd.timestamp.iloc[-1]}")
    print("ANCHOR E0: +11397% / MDD-17.3% / 668 (long+960% short+984%)")
    for pol in pols:
        GAPLOG.clear()
        led = BT.run(make(pol), dd)
        led.to_csv(os.path.join(HERE, f"led_exit_{pol}.csv"), index=False, encoding="utf-8-sig")
        m = metrics(led)
        g = np.array(GAPLOG) if GAPLOG else np.array([0.0])
        nz = g[g > 0]
        flag = "  <<MDD위반" if m['mdd'] < -20.0 else ""
        print(f"[{pol}] {m['n']}거래 ret{m['ret']:+.0f}% MDD{m['mdd']:.1f}%{flag} | long{m['long']:+.0f}% short{m['short']:+.0f}% | {m['reasons']}")
        print(f"     체결현실성: sl<봉범위 청산 {len(nz)}/{len(g)}건 ({len(nz)/len(g)*100:.0f}%), 유리체결 평균{nz.mean() if len(nz) else 0:.0f}bp 최대{nz.max() if len(nz) else 0:.0f}bp")
