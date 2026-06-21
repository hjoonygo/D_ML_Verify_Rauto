# [파일명] rauto_orchestrator.py
# 코드길이: 약 110줄 / 내부버전: rauto_orch_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Rauto 엔진 코어 루프(리플레이): plugin_manager(슬롯봇) + champion(스코어/선택) +
#        safety(가드) + paper_account(집행/청산)을 하나로 묶는다.
#        흐름(매 거래): 레짐판정 → 챔피언 선택(히스테리시스·flat교체) → 안전게이트(허용시 진입)
#                       → 챔피언 봇 신호 → 페이퍼엔진 집행/청산 → 스코어/안전 갱신.
#        ※ 충실 재현 모드: 안전가드 consec=0(비활성), -20%/킬은 게이트(미발동) → 264거래 그대로.
# [Lookahead] 레짐은 진입봉 마감 '이하' asof feat 사용. 스코어는 청산된 손익만 누적.
# ── 사용 파일 ── rauto_contract.py(MarketBar) / rauto_paper_engine.py(PaperAccount)
#                 plugin_manager.py / champion.py / safety.py
# ── 함수 In/Out ──
#  RautoOrchestrator(manager,account,scorer,selector,guard) In: 부품들 → Out: 오케스트레이터
#   .regime_of(row)     In: 거래행 → Out: 레짐문자열(asof feat)
#   .run_replay(df)     In: 거래DF → Out: dict(champion_path,n_entered,n_halted,scorer_table)
#                        ※ account/scorer/guard 상태가 갱신됨
# ── 상수 ── 없음
# ─────────────────────────────────────────────────────────────────────────
import pandas as pd
from rauto_contract import MarketBar


class RautoOrchestrator:
    def __init__(self, manager, account, scorer, selector, guard):
        self.manager = manager
        self.account = account
        self.scorer = scorer
        self.selector = selector
        self.guard = guard

    def regime_of(self, row) -> str:
        f = row.get("feat")
        return f if isinstance(f, str) else "NA"

    def run_replay(self, df) -> dict:
        champ = None
        n_entered = 0
        n_halted = 0
        champ_path = []
        for _, row in df.iterrows():
            regime = self.regime_of(row)
            flat = (self.account.pos is None)             # 원자적 리플레이 → 거래간 항상 flat
            cands = self.manager.loaded_slots()
            champ = self.selector.select(cands, regime, self.scorer, champ, flat)
            champ_path.append(champ)

            if not self.guard.allow_entry():              # 안전게이트(킬/-20%/연속손실)
                n_halted += 1
                continue
            bot = self.manager.get(champ) if champ is not None else None
            if bot is None:
                continue

            aux = {
                "side": int(row["side"]),
                "feat": row.get("feat"),
                "dev": (None if pd.isna(row.get("dev")) else float(row.get("dev"))),
                "regime_dir": (None if pd.isna(row.get("regime_dir")) else int(row.get("regime_dir"))),
            }
            bar = MarketBar(ts=row["entry_t"], tf="8h", regime=regime, aux=aux)
            sig = bot.on_bar(bar)
            if sig is None:
                continue
            ep = row.get("entry_price", 0.0)
            fill = self.account.open(sig, ts=row["entry_t"], price=float(ep if ep == ep else 0.0))
            bot.on_fill(fill)
            p = self.account.resolve_replay(R=float(row["R"]), mae=float(row["mae"]), fund=float(row["fund"]))
            n_entered += 1

            # 챔피언 스코어(레짐별) + 안전 갱신
            self.scorer.update(champ, regime, p if p is not None else 0.0)
            _, mdd, _ = self.account.metrics()
            self.guard.on_equity(mdd)
            self.guard.on_trade(p if p is not None else 0.0)

        return {
            "champion_path": champ_path,
            "n_entered": n_entered,
            "n_halted": n_halted,
            "unique_champions": sorted(set(c for c in champ_path if c is not None)),
            "scorer_table": self.scorer.table(),
        }
