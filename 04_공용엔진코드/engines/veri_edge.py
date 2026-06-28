# -*- coding: utf-8 -*-
# [veri_edge.py] ★수익률·알파 검증 통합 공용엔진 (캡틴 지시 2026-06-28).
#   목적: 봇 거래원장(ledger)을 입력받아 '수익률(%)로' 엣지를 정직 검증.
#   ★내장 규칙(단일출처 CLAUDE.md):
#     · #5 알파체크 = post-2024(ETF후)만 · #6 헤드라인 = OOS(held-out)만, 천장은 '실전아님' 보조라벨
#     · #7 보고 = 종합 + post-2024 매월 · §26 MDD 4단 · ★슬립근사 적용값 병기(§19, 캡틴 2026-06-28)
#     · §16 봇 식별이름 = (봇명)@ETF
#   ★구조(충돌차단): 거래생성 안 함(원장만·§15.1) · 외부import0(numpy/pandas만) · 앵커게이트(§15.2) ·
#     bot_trust_gates(구조관문)와 역할분리.
#   ★사이징 = 격리마진·강제청산 (rauto_paper_engine/liq_eval 1:1, 앵커 +1851.6%로 검증).
#   ★슬립근사(현실) = 시장청산(taker) 거래에 SLIP_REAL bp 추가차감(진입 지정가=메이커=무슬립).
#     기본 10bp = 보수적 현실가정(§15.4 '0~20bp 견고' 범위 내, flash-crash 꼬리는 미반영=레버상한으로 방어).
import numpy as np
import pandas as pd


class VeriEdge:
    ETF = pd.Timestamp("2024-01-01")
    MMR_T1, MMR_T2, TIER, COST, SLIP = 0.004, 0.005, 50000.0, 0.0014, 0.0005   # 격리마진(검증 1:1)
    SLIP_REAL = 10.0   # ★기본 슬립근사 bp(시장청산). 캡틴이 임계선 조절 가능.
    REQUIRED = ["et", "side", "R", "mae", "fund"]
    _MARKET_KEYS = ("stop", "fib", "sl")   # 시장청산(taker) 사유 키워드

    def __init__(self, ledger):
        self.L = self._norm(ledger)

    def _norm(self, L):
        L = L.copy()
        miss = [c for c in self.REQUIRED if c not in L.columns]
        if miss:
            raise ValueError(f"[VeriEdge] 원장 컬럼 누락 {miss} — 봇 계약 = et,xt,side,entry,exit,R,mae,fund,reason")
        L["et"] = pd.to_datetime(L["et"])
        L = L.sort_values("et").reset_index(drop=True)
        L["mkey"] = L["et"].dt.strftime("%Y-%m")
        # 시장청산 플래그(슬립 적용 대상). reason 없으면 보수적으로 전부 시장청산 간주.
        if "reason" in L.columns:
            r = L["reason"].astype(str).str.lower()
            L["_market"] = r.apply(lambda s: any(k in s for k in self._MARKET_KEYS)) | ~r.str.contains("tp|target|limit|early")
        else:
            L["_market"] = True
        return L

    # ── 사이징 (격리마진 강제청산, 슬립근사 옵션) ──
    def _liq(self, sub, size_pct, lev, slip_bp=0.0):
        if len(sub) == 0:
            return 0.0, 0.0, 0, {}
        exp = size_pct / 100.0 * lev
        R = sub["R"].values - (slip_bp / 1e4) * sub["_market"].values.astype(float)   # ★시장청산에 슬립근사
        MAE, FUND, MK = sub["mae"].values, sub["fund"].values, sub["mkey"].values
        bal = peak = 10000.0; mdd = 0.0; nliq = 0; mfac = {}
        for i in range(len(R)):
            mmr = self.MMR_T2 if exp * bal > self.TIER else self.MMR_T1
            hsd = 1.0 / lev - mmr - self.SLIP
            if MAE[i] <= -hsd:
                p = -exp * (hsd + self.COST + abs(FUND[i])); nliq += 1
            else:
                p = R[i] * exp
            bal *= (1.0 + p)
            if bal > peak: peak = bal
            dd = bal / peak - 1.0
            if dd < mdd: mdd = dd
            mfac[MK[i]] = mfac.get(MK[i], 1.0) * (1.0 + p)
            if bal <= 0:
                return -100.0, -100.0, nliq, {}
        return (bal / 10000.0 - 1.0) * 100.0, mdd * 100.0, nliq, mfac

    def _slice(self, lo=None, hi=None):
        L = self.L; m = pd.Series(True, index=L.index)
        if lo is not None: m &= L["et"] >= pd.Timestamp(lo)
        if hi is not None: m &= L["et"] < pd.Timestamp(hi)
        return L[m]

    # ── 1. 앵커검증 게이트 (§15.2) ── (앵커는 무슬립=무손상 기준)
    def anchor_check(self, size_pct, lev, expect_ret, tol=1.0):
        tot, _, _, _ = self._liq(self.L, size_pct, lev, slip_bp=0.0)
        ok = abs(tot - expect_ret) <= tol
        return {"pass": bool(ok), "got_%": round(tot, 1), "expect_%": expect_ret,
                "note": "PASS=사이징·원장 정확" if ok else "FAIL=불일치 → 위 분석 전부 무효(§15.2)"}

    # ── 2. 기간별 수익률 (#5) — 슬립근사 적용 ──
    def returns_by_period(self, size_pct, lev, slip_bp=None):
        sb = self.SLIP_REAL if slip_bp is None else slip_bp
        out = {}
        for nm, (lo, hi) in {"전체": (None, None), "2023(ETF전)": (None, "2024-01-01"),
                             "post-2024(ETF후)": ("2024-01-01", None)}.items():
            sub = self._slice(lo, hi); t, mdd, nl, _ = self._liq(sub, size_pct, lev, sb)
            out[nm] = {"수익%_현실": round(t), "MDD%": round(mdd, 1), "청산": nl, "거래": len(sub)}
        out["_슬립근사bp"] = sb
        return out

    # ── 3. held-out OOS 수익률 (#6 헤드라인) — 슬립0 + 슬립근사 병기 ──
    def heldout_oos(self, size_pct, lev, train_end="2025-01-01", slip_bp=None):
        sb = self.SLIP_REAL if slip_bp is None else slip_bp
        te = self._slice(train_end, None)
        t0, m0, _, _ = self._liq(te, size_pct, lev, 0.0)
        tr, mr, _, _ = self._liq(te, size_pct, lev, sb)
        return {"label": "OOS(held-out·실전 헤드라인)", "거래": len(te),
                "test_슬립0_%": round(t0), "test_슬립0_MDD%": round(m0, 1),
                "test_현실_%": round(tr), "test_현실_MDD%": round(mr, 1), "슬립근사bp": sb,
                "주의": "live<백테 · 단일split · flash-crash 꼬리 미반영(레버상한으로 방어)"}

    # ── 4. 종합 + post-2024 매월 (#7) — 슬립근사 적용 ──
    def monthly_post2024(self, size_pct, lev, slip_bp=None):
        sb = self.SLIP_REAL if slip_bp is None else slip_bp
        sub = self._slice("2024-01-01", None)
        t0, _, _, _ = self._liq(sub, size_pct, lev, 0.0)
        tot, mdd, nl, mfac = self._liq(sub, size_pct, lev, sb)
        rows = []; eq = 1.0
        for m in sorted(mfac):
            g = sub[sub["mkey"] == m]; mret = (mfac[m] - 1.0) * 100.0; eq *= mfac[m]
            rows.append({"년월": m, "거래": len(g), "월수익%_현실": round(mret, 1), "누적%": round((eq - 1) * 100),
                         "롱": int((g.side == 1).sum()), "숏": int((g.side == -1).sum()), "양수": "O" if mret > 0 else "X"})
        mdf = pd.DataFrame(rows); pos = int((mdf["월수익%_현실"] > 0).sum()) if len(mdf) else 0
        return {"종합": {"수익%_슬립0": round(t0), "수익%_현실": round(tot), "MDD%": round(mdd, 1),
                        "거래": len(sub), "강제청산": nl, "승률%": round((sub.R > 0).mean() * 100) if len(sub) else 0,
                        "슬립근사bp": sb},
                "매월": mdf, "매월양수": f"{pos}/{len(mdf)} ({pos/len(mdf)*100:.0f}%)" if len(mdf) else "0/0"}

    # ── 5. MDD 4단 게이트 (§26, 천장=라벨) — 슬립근사 적용 ──
    def mdd_4gate(self, period_lo="2024-01-01", size_pct=75.0, lev_lo=2, lev_hi=20, slip_bp=None):
        sb = self.SLIP_REAL if slip_bp is None else slip_bp
        sub = self._slice(period_lo, None)
        best = {k: (-1e18,) for k in ["M0", "M30", "M25", "M20"]}
        for lev in range(lev_lo, lev_hi + 1):
            t, mdd, nl, _ = self._liq(sub, size_pct, float(lev), sb)
            if t > best["M0"][0]: best["M0"] = (t, lev, mdd, nl)
            for tag, lim in [("M30", -30), ("M25", -25), ("M20", -20)]:
                if mdd >= lim and t > best[tag][0]: best[tag] = (t, lev, mdd, nl)
        out = {"label": f"★in-sample 천장(레버최적·실전아님·헤드라인금지 §1)·슬립근사{sb}bp"}
        for tag in ["M0", "M30", "M25", "M20"]:
            t = best[tag]
            out[tag] = None if t[0] <= -1e17 else {"수익%": round(t[0]), "lev": t[1], "MDD%": round(t[2], 1), "청산": t[3]}
        return out

    # ── 6. ON vs OFF 기여 (held-out OOS, 슬립근사) ──
    @staticmethod
    def contribution(led_on, led_off, size_pct, lev, train_end="2025-01-01", slip_bp=None):
        on = VeriEdge(led_on).heldout_oos(size_pct, lev, train_end, slip_bp)
        off = VeriEdge(led_off).heldout_oos(size_pct, lev, train_end, slip_bp)
        o, f = on["test_현실_%"], off["test_현실_%"]
        return {"label": f"OOS 수익률 기여(현실·슬립{on['슬립근사bp']}bp)", "OFF_%": f, "ON_%": o,
                "기여%p": o - f, "배수": round(o / f, 2) if f > 0 else None}

    # ── 7. 상관 (포폴, post-2024 월수익·현실) ──
    def correlation(self, other_ledger, size_pct, lev, slip_bp=None):
        a = self.monthly_post2024(size_pct, lev, slip_bp)["매월"].set_index("년월")["월수익%_현실"]
        b = VeriEdge(other_ledger).monthly_post2024(size_pct, lev, slip_bp)["매월"].set_index("년월")["월수익%_현실"]
        j = pd.concat([a.rename("A"), b.rename("B")], axis=1).fillna(0.0)
        if len(j) < 3:
            return {"pearson": None, "spearman": None, "개월": len(j), "주의": "표본<3"}
        return {"pearson": round(j["A"].corr(j["B"]), 3), "spearman": round(j["A"].corr(j["B"], method="spearman"), 3), "개월": len(j)}

    # ── 8. 표준 리포트 (헤드라인=OOS현실 / 종합+매월 슬립병기 / 천장 보조) ──
    def report(self, size_pct, lev, anchor_result=None, train_end="2025-01-01", slip_bp=None):
        sb = self.SLIP_REAL if slip_bp is None else slip_bp
        out = ["=" * 70, f"[Veri_edge 수익률 검증]  헤드라인=OOS현실(슬립{sb}bp) · 천장=보조(실전아님)", "=" * 70]
        if anchor_result is not None:
            a = anchor_result
            out.append(f"[0]앵커검증(사이징모델): {'PASS' if a['pass'] else 'FAIL'} (got {a['got_%']}% / expect {a['expect_%']}%)")
            if not a["pass"]:
                out.append("  → ★FAIL: 사이징 불일치 = 아래 전부 무효(§15.2)."); return "\n".join(out)
        o = self.heldout_oos(size_pct, lev, train_end, sb)
        out.append(f"\n[★헤드라인·OOS held-out test] (lev{lev})")
        out.append(f"   슬립0(낙관)  = {o['test_슬립0_%']:+,}% (MDD{o['test_슬립0_MDD%']}%)")
        out.append(f"   ★현실(슬립{sb}bp) = {o['test_현실_%']:+,}% (MDD{o['test_현실_MDD%']}%)  ← ★캡틴 기준값 · {o['거래']}거래")
        out.append(f"   {o['주의']}")
        mm = self.monthly_post2024(size_pct, lev, sb)
        out.append(f"\n[종합 post-2024] 슬립0 {mm['종합']['수익%_슬립0']:+,}% / ★현실(슬립{sb}bp) {mm['종합']['수익%_현실']:+,}% "
                   f"· 승률{mm['종합']['승률%']}% · {mm['종합']['거래']}거래 · 강제청산{mm['종합']['강제청산']} (★in-sample)")
        out.append(f"[매월 양수] {mm['매월양수']}  (§0 목표 · 현실 슬립{sb}bp 적용)")
        out.append("[post-2024 매월 — 현실(슬립근사 적용)]"); out.append(mm["매월"].to_string(index=False))
        g = self.mdd_4gate(size_pct=75.0, slip_bp=sb)
        out.append(f"\n[보조·{g['label']}]")
        for tag in ["M0", "M30", "M25", "M20"]:
            v = g[tag]; out.append(f"  {tag}: " + ("없음" if v is None else f"{v['수익%']:+,}% @lev{v['lev']}/sz75 MDD{v['MDD%']}% 청산{v['청산']}"))
        return "\n".join(out)

    # ── 9. ★인증 이름표 (캡틴 채택 2026-06-28: OOS×현실슬립×보수사이징 → 예상 월복리수익률 + 레짐별) ──
    def nameplate(self, name, size_pct, lev, train_end="2025-01-01", slip_bp=None, desc=""):
        """봇 인증 이름표. 기준 = held-out OOS(test) × 현실슬립 × 보수사이징(lev지정).
           예상 월복리수익률 = OOS 총수익을 OOS 개월수로 복리환산. ledger에 'regime' 컬럼 있으면 레짐별도 산출.
           ★혼동방지: 이 수치만이 '인증값'. train·천장·슬립0은 인증 아님."""
        sb = self.SLIP_REAL if slip_bp is None else slip_bp
        te = self._slice(train_end, None)
        tot, mdd, nl, mfac = self._liq(te, size_pct, lev, sb)
        nmo = len(mfac)
        mcomp = lambda t, k: round((((1 + t / 100.0) ** (1.0 / k) - 1) * 100.0), 2) if k > 0 and (1 + t / 100.0) > 0 else None
        out = {"봇": name, "한줄소개": desc,
               "예상_월복리수익률%": mcomp(tot, nmo),
               "OOS_총수익%": round(tot), "OOS_개월": nmo, "OOS_MDD%": round(mdd, 1),
               "사이징": f"lev{lev}/sz{int(size_pct)}", "슬립근사bp": sb, "강제청산": nl,
               "기준": "held-out OOS(test) × 현실슬립 × 보수사이징 (train·천장·슬립0=인증아님)"}
        # ★레짐별 = post-2024 전체(28mo) in-sample 패턴(상승/하락/횡보 표본 확보·Rauto2 REG_MONTHLY용).
        #   헤드라인(예상_월복리수익률)은 OOS(2025+) 그대로. 레짐별만 표본 위해 28mo(기존 REG_MONTHLY도 in-sample 관례).
        if "regime" in self.L.columns:
            full = self._slice("2024-01-01", None)
            _, _, _, fmfac = self._liq(full, size_pct, lev, sb)
            mon_reg = full.groupby("mkey")["regime"].agg(lambda s: s.value_counts().idxmax())
            reg = {}
            for rg in ["상승", "하락", "횡보"]:
                months = [mm for mm in fmfac if str(mon_reg.get(mm)) == rg]
                if not months:
                    reg[rg] = {"예상_월복리%": None, "개월": 0, "거래": int((full["regime"] == rg).sum())}
                    continue
                facs = np.array([fmfac[mm] for mm in months])
                gm = (facs.prod() ** (1.0 / len(months)) - 1.0) * 100.0 if (facs > 0).all() else None
                reg[rg] = {"예상_월복리%": round(gm, 2) if gm is not None else None,
                           "개월": len(months), "거래": int((full["regime"] == rg).sum())}
            out["레짐별"] = reg
            out["레짐별_주의"] = "레짐별=post-2024 28mo in-sample 패턴(헤드라인 12.29%=OOS). 표본 적은 레짐은 노이즈."
        return out
