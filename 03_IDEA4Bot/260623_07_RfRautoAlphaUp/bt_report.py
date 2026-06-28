# -*- coding: utf-8 -*-
# [bt_report.py] ★백테 마스터 시스템 (캡틴 지시 2026-06-24). 백테 1회 = 모든 산출 자동저장.
#   1) 거래원장 CSV  2) 그 원장기준 Pine(지시 스타일)  3) 통합 월별표(총합/롱/숏 각 승률·PF·손익비·수익금·누적 + 비용통계)
#   4) 저장: D:\ML\RfRauto\00_WorkHstr\BackTest_Output\YYMMDD_NN_명칭\ + 00_WorkHstr\(YYYYMMDDHHMM).txt + 00WorkHstr_INDEX.txt
#   사용: python bt_report.py "백테명칭" [cfg.json | sig_tf pivot_tf N f1 f2 f3 atrm er_gate size lev]
#         (config 생략시 best_params_full.json)
import os, sys, json
from datetime import datetime
sys.path.insert(0, r"D:\ML\RfRauto\04_공용엔진코드\engines")
sys.path.insert(0, r"D:\ML\RfRauto\03_IDEA4Bot\260623_07_RfRautoAlphaUp")
sys.path.insert(0, r"D:\ML\Verify\02 20260618일 이전작업\07 Rauto\07Prj_Ch4_RunAWS_Stg17_ImpatientFork\bots")
import numpy as np, pandas as pd
from fib_replay_1m import load_1m, load_funding
import bt_full as B
import make_pine as MP
import make_chart_html as CH
import rauto_paper_engine as PE
from rauto_contract import Signal, Action, Side

HERE = os.path.dirname(os.path.abspath(__file__))
WH = r"D:\ML\RfRauto\00_WorkHstr"
BTO = os.path.join(WH, "BackTest_Output")
INDEX = os.path.join(WH, "00WorkHstr_INDEX.txt")
MK, TK, SPRD = 0.0002, 0.0004, 0.0001
KEYS = ["sig_tf", "pivot_tf", "N", "fib1", "fib2", "fib3", "init_atr_mult", "er_gate", "size_pct", "lev"]


def _p(*a): print(*a, flush=True)


def parse_cfg(args):
    if len(args) >= 10:
        v = args[:10]
        return dict(sig_tf=int(v[0]), pivot_tf=int(v[1]), N=int(v[2]), fib1=float(v[3]), fib2=float(v[4]),
                    fib3=float(v[5]), init_atr_mult=float(v[6]), er_gate=float(v[7]), size_pct=float(v[8]), lev=float(v[9]))
    if len(args) == 1 and args[0].endswith(".json"):
        return json.load(open(args[0]))
    return json.load(open(os.path.join(HERE, "best_params_full.json")))


def per_trade(T, cfg):
    """거래별 순손익$(현실)·손익금$(낙관무비용)·비용성분. PaperAccount 격리마진·강제청산 2회(net/gross)."""
    expo = cfg["size_pct"] / 100.0 * cfg["lev"]
    an = PE.PaperAccount(10000.0); ag = PE.PaperAccount(10000.0); rows = []
    for r in T.sort_values("et").itertuples():
        side = int(r.side); bn = an.bal; bg = ag.bal; notion = expo * bn
        # net(현실)
        an.open(Signal(Action.ENTER, side=Side(side), size_pct=cfg["size_pct"], leverage=cfg["lev"]), ts=None, price=100.0)
        an.resolve_replay(R=float(r.R), mae=float(r.mae), fund=float(r.fund))
        # gross(무비용 상한) — ★early_tp/tp_frac 블렌드 일관(gross_R). 없으면 x_int폴백(하위호환).
        Rg = float(r.gross_R) if ("gross_R" in T.columns and not pd.isna(r.gross_R)) else side * (float(r.x_int) - float(r.entry)) / float(r.entry)
        ag.open(Signal(Action.ENTER, side=Side(side), size_pct=cfg["size_pct"], leverage=cfg["lev"]), ts=None, price=100.0)
        ag.resolve_replay(R=Rg, mae=float(r.mae), fund=0.0)
        # 비용 성분(명목×율)
        lim_n = 1; lim_fee = MK * notion; mkt_n = 0; mkt_fee = 0.0; slip = 0.0
        if r.reason == "fibstop":
            mkt_n = 1; mkt_fee = (TK + SPRD) * notion
            slip = max(0.0, side * (float(r.x_int) - float(r.exit)) / float(r.entry)) * notion
        else:
            lim_n += 1; lim_fee += MK * notion
        rows.append(dict(month=pd.Timestamp(r.et).strftime("%Y-%m"), side=("롱" if side == 1 else "숏"),
                         net=an.bal - bn, gross=ag.bal - bg, lim_n=lim_n, lim_fee=lim_fee,
                         mkt_n=mkt_n, mkt_fee=mkt_fee, slip=slip, fund=float(r.fund) * notion))
    return pd.DataFrame(rows), an, ag


def grp(g):
    n = len(g); wins = g.net[g.net > 0]; loss = g.net[g.net < 0]
    pf = wins.sum() / abs(loss.sum()) if loss.sum() != 0 else np.inf
    pr = (wins.mean() / abs(loss.mean())) if (len(wins) and len(loss)) else np.nan
    return n, (100 * len(wins) / n if n else 0), pf, pr, g.net.sum()


def unified_table(L):
    """월별 통합표: 총합/롱/숏(거래·승률·PF·손익비·수익금·누적) + 비용통계."""
    months = sorted(L.month.unique()); rows = []
    cumT = cumL = cumS = 0.0
    for m in months:
        gm = L[L.month == m]; gL = gm[gm.side == "롱"]; gS = gm[gm.side == "숏"]
        nT, wT, pfT, prT, sT = grp(gm); nL, wL, pfL, prL, sL = grp(gL); nS, wS, pfS, prS, sS = grp(gS)
        cumT += sT; cumL += sL; cumS += sS
        c = {"년월": m,
             "총합_거래수": nT, "총합_승률(%)": round(wT), "총합_수익팩터(PF)": round(pfT, 2),
             "총합_손익비": round(prT, 2), "총합_수익금($)": round(sT), "총합_누적수익금($)": round(cumT),
             "롱_거래수": nL, "롱_승률(%)": round(wL), "롱_수익팩터(PF)": round(pfL, 2),
             "롱_손익비": round(prL, 2), "롱_수익금($)": round(sL), "롱_누적수익금($)": round(cumL),
             "숏_거래수": nS, "숏_승률(%)": round(wS), "숏_수익팩터(PF)": round(pfS, 2),
             "숏_손익비": round(prS, 2), "숏_수익금($)": round(sS), "숏_누적수익금($)": round(cumS),
             "지정가_체결횟수": int(gm.lim_n.sum()), "지정가_수수료($)": round(gm.lim_fee.sum(), 1),
             "시장가_체결횟수": int(gm.mkt_n.sum()), "시장가_수수료($)": round(gm.mkt_fee.sum(), 1),
             "슬리피지($)": round(gm.slip.sum()), "펀딩비($)": round(gm.fund.sum(), 1),
             "손익금_무비용($)": round(gm.gross.sum()), "총비용($)": round(gm.gross.sum() - gm.net.sum()),
             "순손익금_현실($)": round(gm.net.sum())}
        rows.append(c)
    return pd.DataFrame(rows)


def main():
    if len(sys.argv) < 2:
        _p("사용: python bt_report.py \"백테명칭\" [cfg.json | sig_tf ... lev]"); return
    name = "".join(ch for ch in sys.argv[1] if ch.isalnum() or ch in "_-")[:40] or "backtest"
    cfg = parse_cfg(sys.argv[2:])
    today = datetime.now().strftime("%y%m%d"); ts = datetime.now().strftime("%Y%m%d%H%M")
    os.makedirs(BTO, exist_ok=True)
    nn = len([d for d in os.listdir(BTO) if d.startswith(today + "_")]) + 1
    base = f"{today}_{nn:02d}_{name}"   # ★캡틴 명명규칙: YYMMDD_백테횟수_백테명칭 (모든 산출물 머리)
    folder = os.path.join(BTO, base); os.makedirs(folder, exist_ok=True)
    _p(f"[config] " + " ".join(f"{k}={cfg[k]}" for k in KEYS))
    d1m = load_1m(); fund = load_funding()
    _p("[백테] 전체거래 생성중(현실비용·실펀딩·1m체결·격리마진 강제청산)…")
    T = B.gen_trades(d1m, fund, cfg["sig_tf"], cfg["pivot_tf"], cfg["N"], (cfg["fib1"], cfg["fib2"], cfg["fib3"]),
                     cfg["init_atr_mult"], er_gate=cfg["er_gate"], capture_fills=True)
    expo = cfg["size_pct"] / 100.0 * cfg["lev"]
    # 1) 거래원장 CSV
    led = T.drop(columns=["fills"]).copy()
    led.to_csv(os.path.join(folder, f"{base}_거래원장.csv"), index=False, encoding="utf-8-sig")
    # 통합표
    L, an, ag = per_trade(T, cfg)
    U = unified_table(L)
    U.to_csv(os.path.join(folder, f"{base}_월별통합표.csv"), index=False, encoding="utf-8-sig")
    # 2) Pine (TradingView용 — 캡틴은 TV에서 연구). HTML/크롬오픈은 --html 옵션일 때만(기본 OFF).
    pine_path = os.path.join(folder, f"{base}.pine")
    MP.build_pine(T, expo, out=pine_path, title=f"Rauto {name}")
    html_path = None
    if "--html" in sys.argv:
        html_path = os.path.join(folder, f"{base}_차트.html")
        CH.build_html(d1m, T, expo, out=html_path, pine_text=open(pine_path, encoding="utf-8").read(), title=f"Rauto {name}")
    # 요약
    ret, mdd, cal = an.metrics(); gret = ag.metrics()[0]
    def pf(s): g = s[s > 0].sum(); b = -s[s < 0].sum(); return g / b if b > 0 else np.inf
    head = (f"[백테명] {today}_{nn:02d}_{name}\n[config] " + " ".join(f"{k}={cfg[k]}" for k in KEYS) +
            f"\n[조건] 4h/눌림목·현실비용(maker2/taker4/스프1bp)·실펀딩·1m체결·격리마진 강제청산\n"
            f"[총괄] 거래 {len(L)}·승률{100*(L.net>0).mean():.0f}%·PF{pf(L.net):.2f}·복리{ret:+.1f}%(${an.bal:,.0f})·MDD{mdd:.1f}%·Calmar{cal:.1f}·강제청산{an.n_liq}회\n"
            f"[비용] 순손익${L.net.sum():+,.0f} = 손익금(무비용)${L.gross.sum():+,.0f} − 총비용${L.gross.sum()-L.net.sum():,.0f}\n"
            f"[정직] 손익금=이론스톱체결·무비용(달성불가 상한). 순손익=1m실체결+수수료+펀딩(현실). 단일전략 held-out 한계 별도.")
    # 3) 분석 txt(00_WorkHstr) + 폴더에도
    body = head + "\n\n[월별 통합표]\n" + U.to_string(index=False)
    open(os.path.join(WH, f"{ts}_{base}.txt"), "w", encoding="utf-8").write(body)
    open(os.path.join(folder, f"{base}_분석.txt"), "w", encoding="utf-8").write(body)
    # 4) INDEX 한 줄
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}|{today}_{nn:02d}_{name}|백테 거래{len(L)}·PF{pf(L.net):.2f}·복리{ret:+.0f}%·MDD{mdd:.1f}%·순손익${L.net.sum():+.0f}|src=bt_report.py\n"
    with open(INDEX, "a", encoding="utf-8") as f: f.write(line)
    _p("\n" + "=" * 60)
    _p(head)
    _p("=" * 60)
    _p(f"[저장] {folder}\\  ({base}_거래원장.csv · {base}_월별통합표.csv · {base}.pine · {base}_분석.txt)")
    _p(f"       분석txt: {WH}\\{ts}_{base}.txt · INDEX 한줄 추가")
    _p(f"[TV] {base}.pine → BINANCE:BTCUSDT.P · 시간대 UTC · 4h 에 붙여넣기")


if __name__ == "__main__":
    main()
