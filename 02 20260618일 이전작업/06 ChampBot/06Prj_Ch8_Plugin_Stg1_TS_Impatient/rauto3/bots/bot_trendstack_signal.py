# [파일명] bot_trendstack_signal.py
# 코드길이: 약 300줄 / 내부버전: bot_trendstack_signal_v2 (Stg10 자기완결 사이징) / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 진짜 TrendStack 신호봇 + '완전 자기완결 사이징'. 신호 코어는 trendstack_signal_engine
#        (=SpTrd_Fib_V1_Champion 1:1)을 그대로 쓰고(_step=run_strategy 루프바디 이식, Stg9와 동일·동일거래),
#        사이징은 외부 의존 없이 봇이 직접 계산한다:
#          ① OPVnN  : 7h봉+거래량 → compute_poc(과거60봉,1:1) → dev=(진입가−POC)/ATR(10), rdir=−sign(dev).
#                     |dev|≥OPV & 반대→×n(0.6) / 동일→×N(1.0) / 그외 1.   (trendstack_poc)
#          ② 업트렌드숏컷: 4H봉 → smc_structure(swing8,1:1) → feat_struct_8(shift8,실시간安).
#                     feat=='uptrend' & side=SHORT → ×SH(0.0=스킵).         (trendstack_regime)
#        → 7h(신호+POC) + 4H(장세) '이중 리샘플'. base 노출 EXP1.559(7.0864%×22).
# [미래참조] 신호·POC·feat 모두 진입봉/그 시점 과거값. POC는 과거60봉, feat는 shift(8) 지연확정.
#   ※라이브 봉 경계(7h/4H) 원점은 PC 과거 리샘플과 일치하는지 캘리브레이션 필요(아래 한계). 신호≡소스·OPVnN발동수는 검증됨.
# ── 사용 파일 ── trendstack_signal_engine(신호) / trendstack_poc(POC·dev) / trendstack_regime(feat_struct) / rauto_contract
# ── 함수 In/Out ──
#  TrendStackSignalBot(BotPlugin)
#   .on_init(ctx)                         상태·설정 초기화
#   .on_bar(market: MarketBar(1m))->Signal|None   7h/4H 이중 누적, 7h마감 시 신호+사이징
#   ._step(i,arr,sig,dz_oi,eh)            신호 per-bar 상태머신(run_strategy 루프바디 1:1)
#   ._compute_size(side, entry_i, sig)    라이브 POC/dev(OPVnN)+feat_struct(숏컷) → (size_pct, lev, 디버그)
#   .replay_7h(df7h, oi_arr, **gate)      검증용: 신호 거래(소스 대조, 사이징無)
#   .opvnn_mult(dev, rdir, side)          OPVnN 배수(devledger 발동수 대조용)
# ── 상수 ── BASE_SIZE_PCT/BASE_LEV/SH/OPV/NMULT/N_BOOST/SWING_LEN/BUCKET_7H/BUCKET_4H
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
import trendstack_poc as P
import trendstack_regime as RG
from rauto_contract import BotPlugin, Signal, Action, Side, MarketBar

BASE_SIZE_PCT = 7.0864      # 증거금 % (= EXP 1.559 / 레버 22)
BASE_LEV = 22.0
SH = 0.0                    # 업트렌드 숏 컷 배수 (0.0 = 스킵)
OPV = 0.25                  # OPVnN dev 임계
NMULT = 0.60                # 반대방향(역회귀) 수량 배수 n
N_BOOST = 1.00              # 동일방향(회귀) 수량 배수 N (확정 1.0)
SWING_LEN = 8               # feat_struct 스윙길이
BUCKET_7H = 420
BUCKET_4H = 240


class TrendStackSignalBot(BotPlugin):
    META = {"name": "TrendStack", "version": "ch3s10-selfcontained", "timeframe": "7h",
            "needs": ["oi", "volume"], "engine": "SpTrd_Fib_V1_Champion(1:1)",
            "sizing": "POC/dev(OPVnN)+feat_struct8(uptrend-short-cut), self-contained"}

    # ── 라이프사이클 ──
    def on_init(self, ctx=None):
        ctx = ctx or {}
        c = ctx.get("config", {})
        self.base_size_pct = c.get("base_size_pct", BASE_SIZE_PCT)
        self.base_lev = c.get("leverage", BASE_LEV)
        self.sh = c.get("sh", SH)
        self.opv = c.get("opv", OPV)
        self.nmult = c.get("nmult", NMULT)
        self.n_boost = c.get("n_boost", N_BOOST)
        self.swing_len = c.get("swing_len", SWING_LEN)
        self.poc_lb = c.get("poc_lb", P.POC_LB)
        self.poc_bins = c.get("poc_bins", P.POC_BINS)
        # 신호 게이트(확정설정): OI무덤[0,1) + ER0.45
        self.gate_mode = c.get("gate_mode", "er")
        self.gate_er = c.get("gate_er", 0.45)
        self.gate_adx = c.get("gate_adx", E.ADX_TREND)
        self.dz_lo = c.get("dz_lo", E.DZ_LO)
        self.dz_hi = c.get("dz_hi", E.DZ_HI)
        self.fib = c.get("fib", E.FIB)
        self.short_mode = c.get("short_mode", "none")
        self.short_adx = c.get("short_adx", 0)
        self.short_atrmult = c.get("short_atrmult", 0.8)
        self._reset_state()
        # 7h 버퍼(신호+POC, 거래량 포함)
        self._b7 = None; self._cur7 = None; self._h7 = []; self._oiz = []
        # 4H 버퍼(feat_struct)
        self._b4 = None; self._cur4 = None; self._h4 = []
        self._feat = "range"     # 최신 확정 feat_struct_8

    def _reset_state(self):
        self.pos = 0; self.entry_price = np.nan; self.entry_i = -1
        self.sl = np.nan; self.pb = 0
        self.lastPH = np.nan; self.lastPL = np.nan
        self._trades = []

    # ── OPVnN 배수 (devledger 발동수 대조에도 사용) ──
    def opvnn_mult(self, dev, rdir, side):
        if dev is None or np.isnan(dev):
            return 1.0
        if abs(dev) >= self.opv:
            if side == rdir:        # 동일(회귀방향) → 늘림 N
                return self.n_boost
            if side == -rdir:       # 반대(역회귀) → 줄임 n
                return self.nmult
        return 1.0

    # ── 라이브 사이징: POC/dev(OPVnN) + feat_struct(업트렌드숏컷) ──
    def _compute_size(self, side, entry_i, sig):
        size = self.base_size_pct
        dbg = {}
        # ① 업트렌드 숏 컷 (feat_struct_8)
        if self._feat == "uptrend" and side == -1:
            size *= self.sh
            dbg['uptrend_short_cut'] = self.sh
        # ② OPVnN (라이브 POC/dev)
        h = np.array([r[2] for r in self._h7], float)
        l = np.array([r[3] for r in self._h7], float)
        v = np.array([r[5] for r in self._h7], float)
        mid = (h + l) / 2.0
        dev, rdir = np.nan, 0
        if len(h) > self.poc_lb:
            poc = P.compute_poc(h, l, mid, v, self.poc_lb, self.poc_bins)
            atr_i = sig['atr'][entry_i]
            dev, rdir = P.dev_rdir(self.entry_price, poc[entry_i], atr_i)
            m = self.opvnn_mult(dev, rdir, side)
            size *= m
            dbg.update(dev=round(float(dev), 3) if not np.isnan(dev) else None, rdir=rdir, opvnn_mult=m)
        return size, self.base_lev, dbg

    # ── 신호 per-bar 상태머신 (소스 run_strategy L436-507 이식, Stg9와 동일) ──
    def _step(self, i, arr, sig, dz_oi, eh):
        high, low, close, open_, idx = arr['h'], arr['l'], arr['c'], arr['o'], arr['idx']
        Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']; fib = self.fib

        def n_fund(a, b):
            return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: self.lastPH = ph_conf[i][1]
        if new_pl: self.lastPL = pl_conf[i][1]

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

        if self.pos == 1 and new_pl:
            self.pb += 1; ratio = fib[0] if self.pb == 1 else fib[1] if self.pb == 2 else fib[2]
            if not np.isnan(self.lastPH):
                cand = self.lastPH - ratio * (self.lastPH - pl_conf[i][1])
                self.sl = cand if np.isnan(self.sl) else max(self.sl, cand)
        if self.pos == -1 and new_ph:
            self.pb += 1; ratio = fib[0] if self.pb == 1 else fib[1] if self.pb == 2 else fib[2]
            if not np.isnan(self.lastPL):
                cand = self.lastPL + ratio * (ph_conf[i][1] - self.lastPL)
                self.sl = cand if np.isnan(self.sl) else min(self.sl, cand)

        if self.pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(self.lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(self.lastPL)
            if se and E.short_blocked_combo(sig, i, self.short_adx, self.short_mode, self.short_atrmult):
                se = False
            if dz_oi is not None:
                z = dz_oi[i]
                if not np.isnan(z) and (self.dz_lo <= z < self.dz_hi):
                    if self.gate_mode == 'none':
                        is_trend = True
                    elif self.gate_mode == 'adx':
                        is_trend = sig['adx'][i] >= self.gate_adx
                    elif self.gate_mode == 'er':
                        is_trend = sig['er'][i] >= self.gate_er
                    else:
                        is_trend = True
                    if is_trend:
                        le = False; se = False
            if le or se:
                d = 1 if le else -1
                ep = close[i]
                self.pos = d; self.entry_price = ep; self.entry_i = i; self.pb = 0
                self.sl = ep * (1 - d * E.SL_PCT / 100)
                return 'ENTER', d
        return None

    # ── 검증용: 7h df per-bar 흘려 신호 거래 산출(소스 대조, 사이징 無) ──
    def replay_7h(self, df7h, oi_arr=None, gate_mode='none', gate_er=0.45):
        self._reset_state()
        self.gate_mode = gate_mode; self.gate_er = gate_er
        sig = E.compute_signals(df7h)
        idx = df7h.index
        arr = {'o': df7h['open'].values, 'h': df7h['high'].values,
               'l': df7h['low'].values, 'c': df7h['close'].values, 'idx': idx}
        eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
        for i in range(len(df7h)):
            self._step(i, arr, sig, oi_arr, eh)
        return self._trades

    # ── 라이브: 1m → 7h(신호+POC) + 4H(feat_struct) 이중 누적 ──
    def _bucket(self, ts, width):
        return int(pd.Timestamp(ts).value // 60_000_000_000) // width

    def on_bar(self, market: MarketBar):
        # 4H 갱신(feat_struct)
        b4 = self._bucket(market.ts, BUCKET_4H)
        if self._b4 is None:
            self._b4 = b4; self._cur4 = [market.ts, market.o, market.h, market.l, market.c]
        elif b4 == self._b4:
            self._cur4[2] = max(self._cur4[2], market.h); self._cur4[3] = min(self._cur4[3], market.l); self._cur4[4] = market.c
        else:
            self._close_4h(); self._b4 = b4; self._cur4 = [market.ts, market.o, market.h, market.l, market.c]

        # 7H 갱신(신호+POC)
        b7 = self._bucket(market.ts, BUCKET_7H)
        emitted = None
        vol = market.v or 0.0
        if self._b7 is None:
            self._b7 = b7; self._cur7 = [market.ts, market.o, market.h, market.l, market.c, vol]
        elif b7 == self._b7:
            self._cur7[2] = max(self._cur7[2], market.h); self._cur7[3] = min(self._cur7[3], market.l)
            self._cur7[4] = market.c; self._cur7[5] += vol
        else:
            emitted = self._close_7h(market)
            self._b7 = b7; self._cur7 = [market.ts, market.o, market.h, market.l, market.c, vol]
        return emitted

    def _close_4h(self):
        ts0, o, h, l, c = self._cur4
        self._h4.append([ts0, o, h, l, c])
        if len(self._h4) < (self.swing_len + 3):
            return
        df4 = pd.DataFrame(self._h4, columns=['ts', 'open', 'high', 'low', 'close']).set_index('ts')
        try:
            _, feat = RG.feat_struct_of(df4, self.swing_len)
            self._feat = str(feat.iloc[-1])
        except Exception:
            pass   # 라이브러리/데이터 이슈 시 직전 feat 유지

    def _close_7h(self, market):
        ts0, o, h, l, c, v = self._cur7
        self._h7.append([ts0, o, h, l, c, v])
        z = None
        if isinstance(market.aux, dict) and 'oi_zscore' in market.aux:
            z = market.aux['oi_zscore']
        elif market.oi is not None:
            z = market.oi
        self._oiz.append(np.nan if z is None else float(z))

        df = pd.DataFrame(self._h7, columns=['ts', 'open', 'high', 'low', 'close', 'volume']).set_index('ts')
        if len(df) < (E.LEFT + E.RIGHT + 2):
            return Signal(Action.HOLD, reason="warmup")
        sig = E.compute_signals(df[['open', 'high', 'low', 'close']])
        idx = df.index
        arr = {'o': df['open'].values, 'h': df['high'].values,
               'l': df['low'].values, 'c': df['close'].values, 'idx': idx}
        eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
        i = len(df) - 1
        ev = self._step(i, arr, sig, np.array(self._oiz, dtype=float), eh)
        if ev is None:
            return Signal(Action.HOLD, reason="no_signal")
        kind, payload = ev
        if kind == 'EXIT':
            return Signal(Action.EXIT, side=Side.FLAT, reason=payload)
        d = payload
        size_pct, lev, dbg = self._compute_size(d, i, sig)
        if size_pct <= 0:
            self.pos = 0; self.entry_price = np.nan; self.entry_i = -1; self.sl = np.nan; self.pb = 0
            return Signal(Action.HOLD, reason=f"size0_skip(feat={self._feat})")
        return Signal(Action.ENTER, side=Side(d), size_pct=round(size_pct, 4), leverage=lev,
                      sl=round(float(self.sl), 6), reason=f"entry|feat={self._feat}|{dbg}", confidence=0.6)
