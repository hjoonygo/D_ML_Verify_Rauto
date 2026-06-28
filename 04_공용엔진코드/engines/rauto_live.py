# -*- coding: utf-8 -*-
# [rauto_live.py] ★[0] 관제센터 라이브/리플레이 구동기 — Rauto 구조개혁 ④모듈 (세션 260626_02_Rauto2_Sys).
#   책임 = "시각(now) 기준 b32 대시보드 state.json 생성" = 리플레이(실시간 백테)·라이브의 데이터 출구.
#   ★무손상 철칙(§15.2): 매매 수치는 검증된 batch make_trades 원장 '그대로'. 리플레이는 그 원장을
#     시간순으로 '드러내기'만 한다(재계산·재구현 0). now=마지막이면 ret == 앵커(+1851.6%).
#   ★룩어헤드 차단(안전장치3): state(now)의 px·드러난 거래는 'now까지 마감된 것'만(DataHub 규칙 동일).
#   ★중앙 px 단일출처(차트버그 해소): px는 state["px"] 최상위 1개 — 모든 봇 슬롯이 공유. 봇별로 캔들이
#     달라지던 옛 버그가 구조적으로 사라짐(봇은 거래 trd만 다름).
#   ★per-trade pnl 추출 = rauto_cex의 FeeModel/SlipModel/MarginModel/MK/TK를 '그대로' 호출(재구현 아님).
#     최종잔고가 RautoCEX.run()과 1원단위 일치하는지 테스트가 assert로 가드(LiveAnchorTest).
import pandas as pd
import numpy as np
from rauto_cex import (RautoCEX, SlipModel, FeeModel, MarginModel, MK, TK,
                       MMR_T1, MMR_T2, TIER, LIQ_SLIP, LIQ_COST)


def per_trade_pnl(T, size_pct, lev, slip=None, dd_cut=None):
    """거래원장 → per-trade 계좌손익%(list) + 최종잔고·MDD%·강제청산수.
       RautoCEX.run() 루프를 동일 모델로 1:1 미러(가드=테스트가 final 일치 assert).
       ★dd_cut=(thr,scale): 자기자본 드로다운<=thr면 노출×scale(동적사이징=Rauto 리스크결정·§25). None=고정(기존 동일)."""
    fee = FeeModel()
    slip = slip or SlipModel(0.0, 0.0)
    base_exp = size_pct / 100.0 * lev
    R = T["R"].values.astype(float)
    MAE = T["mae"].values.astype(float)
    FUND = T["fund"].values.astype(float)
    REASON = T["reason"].values if "reason" in T else np.array(["fibstop"] * len(R))
    bal = 10000.0
    peak = 10000.0
    mdd = 0.0
    nliq = 0
    pnl = []
    slip_mkt = slip.market_exit_slip()
    for i in range(len(R)):
        gR = R[i] + MK + TK + FUND[i]
        ec = fee.entry_cost(False)
        xc = fee.exit_cost(REASON[i])
        is_mkt_exit = REASON[i] != "tp"
        R_net = gR - ec - xc - FUND[i] - (slip_mkt if is_mkt_exit else 0.0)
        m = 1.0
        if dd_cut is not None and (bal / peak - 1.0) <= dd_cut[0]:   # 자기 드로다운 컷
            m = dd_cut[1]
        exp = base_exp * m                                          # MarginModel.step 1:1 (m=1이면 기존 동일)
        mmr = MMR_T2 if exp * bal > TIER else MMR_T1
        hsd = 1.0 / lev - mmr - LIQ_SLIP
        if MAE[i] <= -hsd:
            p = -exp * (hsd + LIQ_COST + abs(FUND[i]))
            nliq += 1
        else:
            p = R_net * exp
        bal *= (1.0 + p)
        pnl.append(p * 100.0)
        if bal > peak:
            peak = bal
        dd = bal / peak - 1.0
        if dd < mdd:
            mdd = dd
        if bal <= 0:
            break
    return pnl, bal, mdd * 100.0, nliq


def _to_ms(series_or_ts):
    """pandas datetime(Series/Index/Timestamp, tz-naive UTC) → epoch ms(int)."""
    return (pd.to_datetime(series_or_ts).astype("int64") // 1_000_000)


def _stats(pnl):
    """b32 슬롯 통계(거래·승률·손익비·PF·연속손실·수익률) — control_server._stats 동일 산식."""
    n = len(pnl)
    if not n:
        return dict(trades=0, winrate=0, payoff="-", pf="-", ret=0.0, consec=0)
    w = [x for x in pnl if x > 0]
    l = [x for x in pnl if x < 0]
    payoff = round((sum(w) / len(w)) / abs(sum(l) / len(l)), 1) if (w and l) else ("∞" if w else "-")
    pf = round(sum(w) / abs(sum(l)), 2) if l else ("∞" if w else "-")   # ★손실0(전승)이면 ∞ 표시(캡틴 지시4·1주 PF 안보임 수정)
    r = 1.0
    for x in pnl:
        r *= (1.0 + x / 100.0)
    cc = mx = 0
    for x in pnl:
        cc = cc + 1 if x < 0 else 0
        mx = max(mx, cc)
    return dict(trades=n, winrate=round(len(w) / n * 100), payoff=payoff, pf=pf,
                ret=round((r - 1) * 100, 1), consec=mx)


class BotSlot:
    """봇 1개 = 슬롯. 검증 batch 원장 + per-trade pnl을 미리 산출해두고, reveal(now)로 시간순 드러냄.
       ★봇 무관: 계약 make_trades(d1m,fund)만 맞으면 REVoi·TS·SW 어떤 봇이든 동일하게 받는다."""

    def __init__(self, name, bot, d1m, fund, size_pct, lev, slip=None, dd_cut=None, m20=None, reg_monthly=None):
        self.name = name
        self.size_pct = float(size_pct)
        self.lev = float(lev)
        self.slip = slip or SlipModel(0.0, 0.0)
        self.dd_cut = dd_cut                                                      # ★Rauto 리스크결정(자기DD 동적사이징)
        self._m20_cert = m20                                                      # ★검증(36mo) MDD 기반 M20 인증값(레지스트리 주입). None이면 워밍업 MDD로 대체
        self.reg_monthly = reg_monthly or {}                                      # ★36mo 레짐별 월수익(기대수익률, 챔피언선정Sys)
        T = bot.make_trades(d1m, fund)                                            # ① 검증 원장(앵커)
        if "et" in getattr(T, "columns", []) and len(T):
            T = T.sort_values("et").reset_index(drop=True)
        else:                                                                     # ★거래 0건(짧은 워밍업·조용한 장) 견고처리
            T = pd.DataFrame(columns=["et", "xt", "xt_fill", "side", "entry", "exit", "R", "mae", "fund", "reason"])
        self.T = T
        self.pnl, self.final, self.mdd_full, self.nliq = per_trade_pnl(T, size_pct, lev, self.slip, dd_cut=dd_cut)
        # 시각·가격 사전배열(reveal 빠르게)
        if len(T):
            self.et_ms = _to_ms(T["et"]).values
            xtf = T["xt_fill"] if "xt_fill" in T else T["xt"]
            self.xt_ms = _to_ms(xtf).values
            self.entry = T["entry"].values.astype(float)
            self.exitp = T["exit"].values.astype(float)
            self.side = T["side"].values.astype(int)          # 1=롱 -1=숏
        else:
            self.et_ms = np.array([], dtype="int64"); self.xt_ms = np.array([], dtype="int64")
            self.entry = np.array([], dtype=float); self.exitp = np.array([], dtype=float)
            self.side = np.array([], dtype=int)
        # 거래별 장세 라벨(진입 24h前 대비 가격변화 = 상승/하락/횡보) — 비교카드 '장세별 PF'용
        self.reg_lab = []
        if len(T):
            cl = d1m["close"]
            for t in pd.to_datetime(T["et"]):
                try:
                    c1 = cl.asof(t); c0 = cl.asof(t - pd.Timedelta(days=7))    # 7일추세(cur_regime과 통일)
                    ch = (c1 / c0 - 1.0) * 100.0 if (c0 == c0 and c0) else 0.0   # c0==c0: NaN 아님
                except Exception:
                    ch = 0.0
                self.reg_lab.append("up" if ch > 3.0 else ("down" if ch < -3.0 else "range"))
        self.ret_full = (self.final / 10000.0 - 1.0) * 100.0
        # ★챔피언 자동선발용(결정두뇌): M20 자격 = 검증(36mo) MDD 인증값 우선(§26 챔피언인증=정적), 없으면 워밍업 MDD로 대체.
        self.m20 = bool(self._m20_cert) if self._m20_cert is not None else (self.mdd_full >= -22.0)
        self.reg_ret = {}
        for lab in ("up", "down", "range"):
            vals = [self.pnl[i] for i in range(len(self.reg_lab)) if self.reg_lab[i] == lab]
            self.reg_ret[lab] = float(np.mean(vals)) if vals else None

    def reveal(self, now_ms):
        """now까지: 청산완료(xt<=now) 거래는 trd로, 진행중(et<=now<xt) 1건은 열린포지션으로 드러냄.
           반환 = b32 slot dict (px는 최상위 공유라 여기 없음)."""
        trd = []
        rev_pnl = []
        open_idx = None
        # ★최근 매매현황 표(캡틴 260627_02): 수량·레버·비용 = bal 복리 추적($10k 가상기준).
        _bal = 10000.0
        _exp = self.size_pct / 100.0 * self.lev
        _cols = getattr(self.T, "columns", [])
        _R = self.T["R"].values.astype(float) if ("R" in _cols and len(self.T)) else None
        _gR = self.T["gross_R"].values.astype(float) if ("gross_R" in _cols and len(self.T)) else None
        for i in range(len(self.et_ms)):
            if self.xt_ms[i] <= now_ms:                        # 청산완료
                p = float(self.pnl[i])                          # ★sized 거래수익률(% 단위 = R_net×exp×100)
                qty = (_exp * _bal / self.entry[i]) if self.entry[i] else 0.0   # 진입수량(명목/진입가·dd_cut 근사)
                grp = (float(_gR[i]) * _exp * 100.0) if _gR is not None else ((float(_R[i]) * _exp * 100.0) if _R is not None else p)  # 무비용 %
                trd.append({
                    "et": int(self.et_ms[i]),
                    "xt": int(self.xt_ms[i]),
                    "ep": round(float(self.entry[i]), 2),
                    "xp": round(float(self.entry[i]) * (1.0 + self.side[i] * (float(_gR[i]) if _gR is not None else (float(_R[i]) if _R is not None else 0.0))), 2),  # ★평균체결가=진입×(1+side×gross_R). 분할익절(tp_frac)+조기익절(early_tp) 다중레그라 단일 x_int로는 손익 재구성 불가 → 청산가×수량이 손익과 일치(캡틴 지시 260628). raw 스톱가는 x_int.
                    "side": "L" if self.side[i] == 1 else "S",
                    "pnl": round(p, 2),
                    "lev": self.lev,
                    "qty": round(qty, 3),                       # ★진입수량(소수3)
                    "net_usdt": round((p / 100.0) * _bal, 2),  # ★실수익 USDT($10k 복리기준·실거래 연동前 참고)
                    "net_pct": round(p, 2),                    # ★실수익 수익률%(가상)
                    "gross_pct": round(grp, 2),               # 수익(무비용)%
                    "cost_pct": round(grp - p, 2),            # 비용%(=수익−실수익)
                    "reg": self.reg_lab[i] if i < len(self.reg_lab) else "range",   # 거래별 레짐(챔피언선정Sys)
                })
                rev_pnl.append(self.pnl[i])
                _bal *= (1.0 + p / 100.0)
            elif self.et_ms[i] <= now_ms < self.xt_ms[i]:      # 진행중(열린 포지션)
                open_idx = i
        st = _stats(rev_pnl)
        eq = []
        bal = 10000.0
        for pn in rev_pnl:
            bal *= (1.0 + pn / 100.0)
            eq.append(round(bal, 1))
        # MDD(드러난 구간)
        mdd = 0.0
        peak = 10000.0
        for v in eq:
            if v > peak:
                peak = v
            dd = v / peak - 1.0
            if dd < mdd:
                mdd = dd
        slot = {
            "name": self.name,
            "side": ("L" if self.side[open_idx] == 1 else "S") if open_idx is not None else "-",
            "ret": st["ret"],
            "pnl": 0.0,
            "mdd": round(mdd * 100.0, 1),
            "trades": st["trades"],
            "winrate": st["winrate"],
            "pf": st["pf"],
            "payoff": st["payoff"],
            "consec": st["consec"],
            "entry": round(float(self.entry[open_idx]), 2) if open_idx is not None else None,
            "open_et": int(self.et_ms[open_idx]) if open_idx is not None else None,
            "trd": trd,
            "equity": eq[-300:],
            "eqt": [t["xt"] for t in trd][-300:],
            "kind": "역추세",
        }
        # 최근 7일 통계(비교카드)
        wk_pnl = [self.pnl[i] for i in range(len(self.et_ms))
                  if self.xt_ms[i] <= now_ms and self.et_ms[i] >= now_ms - 7 * 86400000]
        ws = _stats(wk_pnl)
        slot["wk"] = {"trades": ws["trades"], "winrate": ws["winrate"], "ret": ws["ret"],
                      "payoff": ws["payoff"], "pf": ws["pf"], "consec": ws["consec"]}
        # 장세별 PF(상승/하락/횡보) — revealed 거래
        buckets = {"up": [], "down": [], "range": []}
        for i in range(len(self.et_ms)):
            if self.xt_ms[i] <= now_ms and i < len(self.reg_lab):
                buckets[self.reg_lab[i]].append(self.pnl[i])
        reg = {}
        for k, v in buckets.items():
            w = [x for x in v if x > 0]; l = [x for x in v if x < 0]
            reg[k] = round(sum(w) / abs(sum(l)), 2) if l else (None if not w else 9.99)
        slot["reg"] = reg
        slot["reg_ret"] = self.reg_ret      # ★레짐별 기대수익(per-trade 평균) — 챔피언선정Sys '해당레짐 기대순위'
        slot["reg_monthly"] = self.reg_monthly   # ★36mo 레짐별 월수익(기대수익률 %/월)
        slot["m20"] = bool(self.m20)         # M20 자격(챔피언 풀)
        return slot


class Rauto2Live:
    """★Rauto2 라이브/리플레이 구동기. 중앙 1m(단일출처) + 봇 슬롯들 → 시각별 state.json.
       - replay(실시간 백테): now를 과거~현재로 전진시키며 state() 출력.
       - live: 새 1m을 d1m에 덧붙이고(append_1m) 봇 원장 롤링 재계산(rebuild_slot)."""

    def __init__(self, d1m, fund, px_window_min=14 * 1440, champ_mode="recent", m20_thr=-22.0, champ_pin=None):
        self.d1m = d1m.sort_index()
        self.fund = fund
        self.px_window_min = int(px_window_min)               # state.px 최상위 윈도우(분). 기본 14일.
        self.champ_mode = champ_mode                          # ★챔피언 자동선발: recent|regime|maxret (캡틴 260626_02)
        self.champ_pin = champ_pin                            # ★인증봇 고정(캡틴 지시1 260628): 이 이름이 M20풀에 있으면 무조건 챔피언
        self.m20_thr = float(m20_thr)                         # 챔피언 풀 자격 = 전체 MDD ≥ 이 값(같은 위험등급)
        self.slots = []                                       # [BotSlot, ...]
        # 1m 시각 ms 사전배열(윈도우 슬라이싱용)
        self._idx_ms = _to_ms(self.d1m.index).values
        self._o = self.d1m["open"].values.astype(float)
        self._h = self.d1m["high"].values.astype(float)
        self._l = self.d1m["low"].values.astype(float)
        self._c = self.d1m["close"].values.astype(float)

    def add_bot(self, name, bot, size_pct, lev, slip=None, dd_cut=None, m20=None, reg_monthly=None):
        self.slots.append(BotSlot(name, bot, self.d1m, self.fund, size_pct, lev, slip,
                                  dd_cut=dd_cut, m20=m20, reg_monthly=reg_monthly))
        return self.slots[-1]

    def px_window(self, now_ms):
        """★중앙 px(최상위 단일출처): now까지 '마감된' 1m봉만(룩어헤드 차단=label+1m<=now) + 최근 윈도우.
           = label_ms <= now_ms - 60000. 반환 [[ms,o,h,l,c], ...]."""
        closed = now_ms - 60_000                              # 1m봉 마감(label+1분) <= now
        lo = closed - self.px_window_min * 60_000
        sel = (self._idx_ms > lo) & (self._idx_ms <= closed)
        idx = np.nonzero(sel)[0]
        if len(idx) == 0:
            return []
        cap = 8000                                            # ★다운샘플: 긴 윈도우도 ~8000점(폰 대역폭). base분 버킷 OHLC.
        base = max(1, int(np.ceil(len(idx) / cap)))
        if base == 1:
            return [[int(self._idx_ms[i]), round(self._o[i], 1), round(self._h[i], 1),
                     round(self._l[i], 1), round(self._c[i], 1)] for i in idx]
        bms = base * 60_000
        out = []; t0 = None; o = h = l = c = 0.0
        for i in idx:
            bt = int(self._idx_ms[i] // bms) * bms
            if t0 is None or bt != t0:
                if t0 is not None:
                    out.append([int(t0), round(o, 1), round(h, 1), round(l, 1), round(c, 1)])
                t0 = bt; o = self._o[i]; h = self._h[i]; l = self._l[i]; c = self._c[i]
            else:
                h = max(h, self._h[i]); l = min(l, self._l[i]); c = self._c[i]
        if t0 is not None:
            out.append([int(t0), round(o, 1), round(h, 1), round(l, 1), round(c, 1)])
        return out

    def cur_regime(self, now_ms):
        """now 시점 7일 추세 레짐(상승>+3/하락<-3/횡보) — 인과(과거 7일만)."""
        i = int(np.searchsorted(self._idx_ms, int(now_ms), "right")) - 1
        if i <= 0:
            return "range"
        j = int(np.searchsorted(self._idx_ms, int(now_ms) - 7 * 86400000, "right")) - 1
        ch = (self._c[i] / self._c[max(0, j)] - 1.0) * 100.0
        return "up" if ch > 3 else ("down" if ch < -3 else "range")

    def pick_champion(self, now_ms, slots):
        """★챔피언 자동선발(결정두뇌 §25·§26): M20자격 풀에서 레짐/최근수익으로 선택.
           recent=최근2주 최고수익봇 · regime=현레짐 과거최고봇(없으면 최근) · maxret=드러난수익 최고.
           ★같은 위험등급(M20 tier)만 후보 — 레버 섞으면 MDD 폭발(시뮬 검증)."""
        elig = [i for i in range(len(self.slots)) if self.slots[i].m20]
        if not elig:
            elig = list(range(len(self.slots)))
        # ★캡틴 지시1(260628): 인증봇 고정(pin) — pin된 봇이 M20자격 풀에 있으면 무조건 챔피언(천장봇 자동선발 회피).
        if self.champ_pin:
            pinned = [i for i in elig if self.slots[i].name == self.champ_pin]
            if pinned:
                return pinned[0]

        def recent2w(i):
            bs = self.slots[i]; lo = now_ms - 14 * 86400000; r = 1.0
            for k in range(len(bs.xt_ms)):
                if lo <= bs.xt_ms[k] <= now_ms:
                    r *= (1.0 + bs.pnl[k] / 100.0)
            return r

        if self.champ_mode == "regime":
            reg = self.cur_regime(now_ms)
            scored = [(i, self.slots[i].reg_ret.get(reg)) for i in elig]
            have = [(i, s) for i, s in scored if s is not None]
            if have:
                return max(have, key=lambda x: x[1])[0]
            return max(elig, key=recent2w)                    # 레짐 이력 없으면 최근수익 fallback
        if self.champ_mode == "maxret":
            return max(elig, key=lambda i: slots[i]["ret"])
        return max(elig, key=recent2w)                        # 기본 recent(robust·MDD우위)

    def state(self, now_ms, with_px=True):
        """b32 대시보드 state.json dict. px=최상위 공유, slots=각 봇 reveal(now)."""
        slots = [s.reveal(now_ms) for s in self.slots]
        # ★챔피언 자동선발(결정두뇌): M20자격 풀 + 레짐/최근전환 (단순 max ret 아님)
        if slots:
            bi = self.pick_champion(now_ms, slots)
            for i, s in enumerate(slots):
                s["champ"] = (i == bi)
                s["m20"] = bool(self.slots[i].m20)
        st = {
            "slots": slots,
            "live": False,
            "dauto_ok": True,
            "dauto_stale_min": 0,
            "now": int(now_ms),
            "updated": str(pd.Timestamp(now_ms, unit="ms")),
            "champ_mode": self.champ_mode,
            "regime": self.cur_regime(now_ms),
        }
        if with_px:
            st["px"] = self.px_window(now_ms)                 # ★최상위 중앙 px(전 봇 공유)
        return st

    # ── 리플레이(실시간 백테) 시각 생성 ──
    def replay_times(self, step_min=240, start_ms=None, end_ms=None):
        """리플레이용 now 시각열(ms). step_min 간격(기본 4H=신호TF). 데이터 범위 내."""
        a = int(self._idx_ms[0]) if start_ms is None else int(start_ms)
        b = int(self._idx_ms[-1]) if end_ms is None else int(end_ms)
        step = step_min * 60_000
        t = a
        out = []
        while t <= b:
            out.append(t)
            t += step
        if out and out[-1] != b:
            out.append(b)
        return out

    # ── 라이브: 새 1m 덧붙이기 + 봇 롤링 재계산 ──
    def append_1m(self, df_new):
        """Dauto가 수집한 새 1m(OHLC, DatetimeIndex)을 중앙 d1m에 덧붙임(중복 제거)."""
        merged = pd.concat([self.d1m, df_new[["open", "high", "low", "close"]]])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        self.d1m = merged
        self._idx_ms = _to_ms(self.d1m.index).values
        self._o = self.d1m["open"].values.astype(float)
        self._h = self.d1m["high"].values.astype(float)
        self._l = self.d1m["low"].values.astype(float)
        self._c = self.d1m["close"].values.astype(float)

    def rebuild_slot(self, slot_idx, bot):
        """라이브: 덧붙은 d1m으로 해당 봇 원장 재계산(롤링 walk-forward = 실시간 백테).
           ★검증된 make_trades를 전체 데이터에 재호출 → now까지 마감봉만 신호(룩어헤드0). 결과는 reveal로 드러냄."""
        s = self.slots[slot_idx]
        self.slots[slot_idx] = BotSlot(s.name, bot, self.d1m, self.fund, s.size_pct, s.lev, s.slip)
        return self.slots[slot_idx]
