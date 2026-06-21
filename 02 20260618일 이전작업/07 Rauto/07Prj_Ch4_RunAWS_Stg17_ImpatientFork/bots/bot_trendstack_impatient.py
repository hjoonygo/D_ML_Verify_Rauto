# [파일명] bot_trendstack_impatient.py
# 코드길이: 약 80줄 / 내부버전: bot_trendstack_impatient_v1 ("인내심 없는" 분기)
# ─────────────────────────────────────────────────────────────────────────
# [목적] 기존 TrendStack(인내=피벗확정 대기 후 진입)의 분기 변종.
#        ★유일 차이 = 진입 타이밍: 슈퍼트렌드가 그 방향이면 '피벗 새 확정(new_pl/new_ph)'을
#        기다리지 않고 즉시 진입한다(=인내심 없음). 그 외 전부 기존 봇과 1:1 동일.
#        (SL 1%·피보 트레일·trend_flip/SL 청산·OI무덤·ER0.45 게이트·OPVnN 사이징·업트렌드숏컷)
# [무수정 원칙] §8 해시락 봇(bot_trendstack_signal 040da0d2)·엔진(trendstack_signal_engine 7f9192e3)은
#        한 글자도 안 건드린다. 본 파일은 TrendStackSignalBot을 상속해 _step만 오버라이드(래퍼/플러그인).
#        on_bar·_close_7h·_close_4h·_compute_size·replay_7h 전부 부모 것을 그대로 사용
#        (부모의 _close_7h가 self._step을 부르므로 오버라이드가 라이브에도 자동 반영).
# [분기 정의 — 캡틴 기본승인값]
#   · 전 flip 즉시(강도게이트 없음. ML 강신호필터는 N=50 부족으로 폐기).
#   · '즉시'의 구현 = pos==0 & Trend 방향확정 & 직전 스윙(lastPH·lastPL) 존재 & 게이트통과 → close[i] 진입.
#     (flip봉엔 기존대로 EXIT 1신호 → 다음 7h봉에 즉시 ENTER. 단일신호/봉 계약 준수.
#      기존은 새 피벗까지 중앙 9봉=63h 대기 → 본 변종은 +1봉(7h)에 진입 = '갈아타기'의 시간손실 제거.)
# ── 사용 ── test 스크립트에서 TrendStackSignalBot 대신 TrendStackImpatientBot 인스턴스화.
# ─────────────────────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
import trendstack_signal_engine as E
from bot_trendstack_signal import TrendStackSignalBot
from rauto_contract import Signal, Action, Side


class TrendStackImpatientBot(TrendStackSignalBot):
    META = {"name": "TrendStack_IMP", "version": "impatient-v1",
            "timeframe": "7h", "needs": ["oi", "volume"],
            "engine": "SpTrd_Fib_V1_Champion(1:1)",
            "sizing": "POC/dev(OPVnN)+feat_struct8, self-contained",
            "fork": "no-pivot-wait entry (impatient switch)"}

    # ── 신호 per-bar 상태머신: 부모 _step과 1:1 동일, 진입조건만 피벗대기 제거 ──
    def _step(self, i, arr, sig, dz_oi, eh):
        # ── 워밍업 가드(라이브 동치 보존) ──
        # 부모 라이브 경로 _close_7h는 7h누적 len < (LEFT+RIGHT+2)=7 동안 _step을 통째 skip(첫 처리 i=6).
        # replay_7h는 i=0부터 전부 호출하므로, 인내심없는(피벗대기 없는) 진입이 초기봉(i<6)에서 한 번 더
        # 잡혀 라이브≡리플레이가 깨진다. 라이브와 동일하게 i<6을 통째 skip해 동치를 복원한다(라이브 거래 불변).
        if i < (E.LEFT + E.RIGHT + 1):
            return None
        high, low, close, open_, idx = arr['h'], arr['l'], arr['c'], arr['o'], arr['idx']
        Trend = sig['Trend']; ph_conf = sig['ph_conf']; pl_conf = sig['pl_conf']; fib = self.fib

        def n_fund(a, b):
            return int(np.floor(eh[b] / 8.0) - np.floor(eh[a] / 8.0))

        new_ph = i in ph_conf; new_pl = i in pl_conf
        if new_ph: self.lastPH = ph_conf[i][1]
        if new_pl: self.lastPL = pl_conf[i][1]

        # ── 보유 중: 청산(부모와 동일) ──
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

        # ── 피보 트레일(부모와 동일) ──
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

        # ── 진입: ★유일 분기점 — 피벗확정 대기 제거(즉시 갈아타기) ──
        if self.pos == 0:
            # [기존] le = Trend[i]==1 and new_pl and not isnan(lastPH)
            #        se = Trend[i]==-1 and new_ph and not isnan(lastPL)
            # [분기] new_pl/new_ph 대기 제거. 스윙구조(lastPH·lastPL)만 있으면 즉시 진입.
            le = Trend[i] == 1 and not np.isnan(self.lastPH) and not np.isnan(self.lastPL)
            se = Trend[i] == -1 and not np.isnan(self.lastPH) and not np.isnan(self.lastPL)
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
