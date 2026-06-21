# [파일명] bot_trendstack_signal.py
# 코드길이: 약 230줄 / 내부버전: bot_trendstack_signal_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 진짜 TrendStack 신호봇(Rauto BotPlugin). 진입/청산 신호 코어는 trendstack_signal_engine
#        (=SpTrd_Fib_V1_Champion 1:1 추출)을 그대로 쓰고, 그 batch 루프(run_strategy)를
#        라이브용 per-bar 상태머신 `_step`으로 재구성한다. `_step`은 소스 run_strategy의 루프바디
#        (원본 L436-507)를 그대로 옮긴 것이라 '동일 입력→동일 거래'가 보장된다(검증으로 확인).
# [신호] 방향=피벗 슈퍼트렌드. 롱=상승추세+새 피벗저점, 숏=하락추세+새 피벗고점. 청산=trend_flip 또는 SL(초기 ±1% + 피보 트레일링).
#        게이트=OI무덤[0,1)+ER0.45(확정설정). ※진입 결정만 봇이 함 — 분할진입 체결은 엔진(라이브) 몫.
# [사이징] 봇이 결정: base 노출(EXP1.559=7.0864%×22) × 업트렌드숏컷 × OPVnN.
#   · 업트렌드숏컷: regime(feat_struct_8)=='uptrend' & side=SHORT → ×SH(기본 0.0=스킵).  [regime은 market.regime/aux로 공급]
#   · OPVnN(훅): dev=(진입가−POC)/ATR 과 regime_dir 제공 시 |dev|≥OPV(0.25)&side==−regime_dir → ×NMULT(0.6), 아니면 1.0.
#     ※POC/dev 산출코드(07Prj_Ch2_Stg2 devledger 생성기)는 미보유 → '제공되면 적용'하는 훅. 원본도 devledger 없으면 mult=1.
# [미래참조] 신호는 진입봉까지 과거값(엔진과 동일). 라이브 진입가는 종가 기준(분할은 엔진 체결).
# ── 사용 파일 ── trendstack_signal_engine.py(신호코어) / rauto_contract.py(계약)
# ── 함수 In/Out ──
#  TrendStackSignalBot()  BotPlugin
#   .on_init(ctx)   In: {config?}                → 상태 초기화
#   .on_bar(market) In: MarketBar(1m)            → Signal|None (7h 마감 시 결정)
#   ._compute_size(side,regime,dev,regime_dir)   → (size_pct, leverage)
#   .replay_7h(df7h, oi_arr, **gatecfg)          → trades 리스트 (검증용: 소스 run_strategy와 대조)
#   ._step(i, arr, sig, dz_oi, cfg)              → 'ENTER'/'EXIT'/None (run_strategy 루프바디 이식)
# ── 상수 ── BASE_SIZE_PCT / BASE_LEV / SH / OPV / NMULT (사이징 기본값)
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
from rauto_contract import BotPlugin, Signal, Action, Side, MarketBar

# 사이징 기본값 (검증된 +827% 채택값)
BASE_SIZE_PCT = 7.0864     # 증거금 % (= EXP 1.559 / 레버 22)
BASE_LEV = 22.0
SH = 0.0                   # 업트렌드 숏 컷 배수 (0.0 = 스킵)
OPV = 0.25                 # OPVnN dev 임계
NMULT = 0.60               # 역추세 수량 배수
TF_LABEL = "7h"
BUCKET_MIN = 420           # 7h


class TrendStackSignalBot(BotPlugin):
    META = {"name": "TrendStack", "version": "ch3s9-fib-v1", "timeframe": TF_LABEL,
            "needs": ["oi"], "engine": "SpTrd_Fib_V1_Champion(1:1)"}

    # ── 라이프사이클 ──
    def on_init(self, ctx=None):
        ctx = ctx or {}
        c = ctx.get("config", {})
        self.base_size_pct = c.get("base_size_pct", BASE_SIZE_PCT)
        self.base_lev = c.get("leverage", BASE_LEV)
        self.sh = c.get("sh", SH)
        self.opv = c.get("opv", OPV)
        self.nmult = c.get("nmult", NMULT)
        # 게이트(확정설정): OI무덤[0,1) + ER게이트0.45
        self.gate_mode = c.get("gate_mode", "er")
        self.gate_er = c.get("gate_er", E.ER_TREND if False else 0.45)
        self.gate_adx = c.get("gate_adx", E.ADX_TREND)
        self.dz_lo = c.get("dz_lo", E.DZ_LO)
        self.dz_hi = c.get("dz_hi", E.DZ_HI)
        self.fib = c.get("fib", E.FIB)
        # 숏차단(원본 FINAL: none)
        self.short_mode = c.get("short_mode", "none")
        self.short_adx = c.get("short_adx", 0)
        self.short_atrmult = c.get("short_atrmult", 0.8)
        self._reset_state()
        # 라이브 1m→7h 버퍼
        self._cur_bucket = None
        self._cur = None        # [ts0, o, h, l, c]
        self._h7 = []           # 7h OHLC 행 [ts,o,h,l,c]
        self._oiz = []          # 7h별 oi_zscore (게이트용)

    def _reset_state(self):
        self.pos = 0
        self.entry_price = np.nan
        self.entry_i = -1
        self.sl = np.nan
        self.pb = 0
        self.lastPH = np.nan
        self.lastPL = np.nan
        self._trades = []

    # ── 사이징 (봇이 결정) ──
    def _compute_size(self, side, regime=None, dev=None, regime_dir=None):
        size = self.base_size_pct
        # 업트렌드 숏 컷
        if regime == "uptrend" and side == -1:
            size *= self.sh
        # OPVnN (제공 시)
        if dev is not None and regime_dir is not None:
            if abs(dev) >= self.opv and side == -int(regime_dir):
                size *= self.nmult
        return size, self.base_lev

    # ── 신호 per-bar 상태머신: 소스 run_strategy(L436-507) 루프바디 이식 ──
    def _step(self, i, arr, sig, dz_oi, eh):
        high, low, close, open_, idx = arr['h'], arr['l'], arr['c'], arr['o'], arr['idx']
        Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']
        fib = self.fib

        def n_fund(a, b):
            return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: self.lastPH = ph_conf[i][1]
        if new_pl: self.lastPL = pl_conf[i][1]

        if self.pos != 0:
            # trend_flip
            if (self.pos == 1 and Trend[i] == -1) or (self.pos == -1 and Trend[i] == 1):
                px = close[i]; R = self.pos * (px - self.entry_price) / self.entry_price * E.LEVERAGE
                fp = E.FUND_8H * n_fund(self.entry_i, i); R = R - E.COST - fp
                self._trades.append({'entry_t': idx[self.entry_i], 'exit_t': idx[i], 'side': self.pos,
                                     'entry': self.entry_price, 'exit': px, 'R': R, 'reason': 'trend_flip',
                                     'bars': i - self.entry_i, 'fund': fp, 'year': idx[i].year})
                self.pos = 0; self.sl = np.nan; self.pb = 0
                return 'EXIT', 'trend_flip'
            # SL
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

        # 피보 트레일링 SL 갱신
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

        # 진입
        if self.pos == 0:
            le = Trend[i] == 1 and new_pl and not np.isnan(self.lastPH)
            se = Trend[i] == -1 and new_ph and not np.isnan(self.lastPL)
            if se and E.short_blocked_combo(sig, i, self.short_adx, self.short_mode, self.short_atrmult):
                se = False
            # OI 무덤필터 + 게이트
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
                ep = close[i]   # 라이브 진입가=종가(분할 체결은 엔진). 검증도 split='none'과 동일.
                self.pos = d; self.entry_price = ep; self.entry_i = i; self.pb = 0
                self.sl = ep * (1 - d * E.SL_PCT / 100)
                return 'ENTER', d
        return None

    # ── 검증용: 7h df를 per-bar로 흘려 거래 산출 (소스 run_strategy와 대조) ──
    def replay_7h(self, df7h, oi_arr=None, gate_mode='none', gate_er=0.45, gate_adx=None, dz_lo=None, dz_hi=None):
        self._reset_state()
        self.gate_mode = gate_mode; self.gate_er = gate_er
        if gate_adx is not None: self.gate_adx = gate_adx
        if dz_lo is not None: self.dz_lo = dz_lo
        if dz_hi is not None: self.dz_hi = dz_hi
        sig = E.compute_signals(df7h)
        idx = df7h.index
        arr = {'o': df7h['open'].values, 'h': df7h['high'].values,
               'l': df7h['low'].values, 'c': df7h['close'].values, 'idx': idx}
        eh = ((idx - pd.Timestamp('1970-01-01')) / pd.Timedelta(hours=1)).values.astype('float64')
        dz = oi_arr if oi_arr is not None else None
        for i in range(len(df7h)):
            self._step(i, arr, sig, dz, eh)
        return self._trades

    # ── 라이브: 1m → 7h 누적 후 마감 시 신호 ──
    def _bucket(self, ts):
        epoch_min = int(pd.Timestamp(ts).value // 60_000_000_000)
        return epoch_min // BUCKET_MIN

    def on_bar(self, market: MarketBar):
        b = self._bucket(market.ts)
        emitted = None
        if self._cur_bucket is None:
            self._cur_bucket = b
            self._cur = [market.ts, market.o, market.h, market.l, market.c]
        elif b == self._cur_bucket:
            self._cur[2] = max(self._cur[2], market.h)
            self._cur[3] = min(self._cur[3], market.l)
            self._cur[4] = market.c
        else:
            # 직전 7h 봉 마감 → 처리
            emitted = self._close_7h(market)
            self._cur_bucket = b
            self._cur = [market.ts, market.o, market.h, market.l, market.c]
        return emitted

    def _close_7h(self, market):
        ts0, o, h, l, c = self._cur
        self._h7.append([ts0, o, h, l, c])
        # oi_zscore: aux 우선, 없으면 market.oi(이미 z라고 가정), 없으면 NaN
        z = None
        if isinstance(market.aux, dict) and 'oi_zscore' in market.aux:
            z = market.aux['oi_zscore']
        elif market.oi is not None:
            z = market.oi
        self._oiz.append(np.nan if z is None else float(z))

        df = pd.DataFrame(self._h7, columns=['ts', 'open', 'high', 'low', 'close']).set_index('ts')
        if len(df) < (E.LEFT + E.RIGHT + 2):
            return Signal(Action.HOLD, reason="warmup")
        sig = E.compute_signals(df)
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
        # ENTER
        d = payload
        regime = market.regime
        dev = market.aux.get('dev') if isinstance(market.aux, dict) else None
        regime_dir = market.aux.get('regime_dir') if isinstance(market.aux, dict) else None
        size_pct, lev = self._compute_size(d, regime, dev, regime_dir)
        if size_pct <= 0:
            # 업트렌드 숏 컷 등으로 0 → 진입 스킵(보유 시작 안 함). 상태 되돌림.
            self.pos = 0; self.entry_price = np.nan; self.entry_i = -1; self.sl = np.nan; self.pb = 0
            return Signal(Action.HOLD, reason="size0_skip")
        return Signal(Action.ENTER, side=Side(d), size_pct=round(size_pct, 4), leverage=lev,
                      sl=round(float(self.sl), 6), reason="entry", confidence=0.6)
