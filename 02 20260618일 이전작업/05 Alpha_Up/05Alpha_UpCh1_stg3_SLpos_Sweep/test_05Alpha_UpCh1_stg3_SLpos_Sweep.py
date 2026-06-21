# -*- coding: utf-8 -*-
# [FILE] test_05Alpha_UpCh1_stg3_SLpos_Sweep.py
# 코드길이: 약 540줄 | 내부버전명: 05Alpha_Up_Ch1_SLpos_stg3 | 전체 출력, 축약/생략 없음
# ==============================================================================
# [목적] stg2 눌림목봇(롱숏)에서 SL '기준점'을 다양하게 바꿔 A안과 비교한다.
#        사장님 제안: 단계(횟차) 구분 없이 '눌림목→고점(HH) 거리'의 고정 위치에 SL을 일률 적용.
#        위치 4종(0.2/0.3/0.4/0.5, 사장님 지정) + 타이트쪽 3종(0.6/0.7/0.8, 비교용 추가) = 7종.
#        기준선 A안(원본 단계형 0.3→0.5→0.6)과 한 그리드에서 비교. 롱/숏 따로 + 월별 롱/숏 따로.
#
# [SL 모드 정의 — sl_update 어댑터에서만 분기 (Key_05Alpha_UpCh1_stg1 계약구조 준수)]
#   'A_STEP'  = stg2 원본 A안. 단계별 비율 FIB=(0.3,0.5,0.6), 고점기준. 롱 max / 숏 min.
#   'FIXxx'   = 고정위치. 횟차 무관 항상 같은 위치. 위치 p = 눌림목→고점 거리비율.
#       롱: SL = 눌림목 + p*(고점-눌림목)   [p작을수록 눌림목 가까움=여유/깊은손절, p클수록 고점 가까움=타이트]
#       숏: SL = 고점   - p*(고점-눌림목)   (거울상)
#       단, 고정도 비가역 유지: 롱 max(안내림) / 숏 min(안올림). 새 변곡점마다 재계산해 갱신.
#   ※ 수학적 관계: FIXp 는 A안 단일비율 (1-p) 와 동일 위치. 단 A_STEP은 단계마다 비율이 변함(차이점).
#
# [위치 직관] FIX020 깊은손절(여유) ··· FIX050 정중앙 ··· FIX080 얕은손절(타이트)
# [진입/청산/비용/미래참조] stg2(test_..._Vrfy)와 100% 동일. 진입로직 한 줄도 안 바꿈(SL만 변경).
# [PATH] 실행 D:\ML\verify\05Alpha_UpCh1_stg3_SLpos_Sweep\ . 데이터 상위 자동탐색.
# [DATA] 상위 Merged_Data_with_Regime_Features.csv (없으면 merged_data.csv). OHLCV만.
# [OUTPUT] sl_summary.csv + sl_trades.csv + sl_monthly.csv + sl_scenarios.csv → check.py 정리.
# [SPEED] 신호 캐시 1회. 그리드는 거래루프만. SL모드 8종(A_STEP+FIX 7) x 방향 x 진입파라미터.
#
# [FUNCTIONS]
#   find_data/load_1m/resample_tf/rma/compute_rsi/compute_atr/compute_dmi/pivots/precompute  : stg2와 동일
#   sl_update(mode,side,...)  In: 모드,방향,피벗,prevSL  Out: 갱신SL  ★SL 어댑터(A_STEP/FIXxx 분기+비가역+폴백)
#   scen_label/run_bot/agg/monthly/pick_best/main  : stg2와 동일 골격 (SL만 sl_update 경유)
# [변수] pos avg entry_i pb trailSL  lastPH prevPH lastPL prevPL structUp structDn  sl_mode pfix
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)

COMMISSION = 0.0008
START_CAP  = 10000.0
SLPCT      = 1.0
FIB        = (0.3, 0.5, 0.6)      # A_STEP 단계 비율
BAL_SL     = 10.0
TIME_STOP  = 30
WAIT_MAX   = 5
RSI_LEN = 14; ATR_LEN = 14; ADX_LEN = 14; ADX_SMOOTH = 14
PIV_L = 4; PIV_R = 1
TRAIN_YEARS = [2023, 2024]; TEST_YEARS = [2025, 2026]

GRID_TF     = [60, 2*60, 4*60]
GRID_rsiOS  = [35, 40, 45]
GRID_rsiOSs = [55, 60, 65]
GRID_gate   = ['OFF', 'ADX_TREND']
GRID_adxTh  = [20, 25]
GRID_dir    = ['LONG', 'SHORT', 'BOTH']
# ★SL 모드: 기준 A_STEP + 고정위치 7종 (0.2~0.5 사장님지정 + 0.6~0.8 비교추가)
GRID_SLMODE = ['A_STEP', 'FIX020', 'FIX030', 'FIX040', 'FIX050', 'FIX060', 'FIX070', 'FIX080']
FIX_POS = {'FIX020':0.2,'FIX030':0.3,'FIX040':0.4,'FIX050':0.5,'FIX060':0.6,'FIX070':0.7,'FIX080':0.8}

SCEN = ['clean_uptrend','clean_downtrend','choppy_range','strong_breakout',
        'failed_pullback','v_reversal','high_adx','low_adx']


def find_data():
    cands = ["Merged_Data_with_Regime_Features.csv", "merged_data.csv"]
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for c in cands:
            p = os.path.join(d, c)
            if os.path.exists(p):
                return p
    raise FileNotFoundError("상위 D:\\ML\\verify 에 데이터 csv 필요")


def load_1m(path):
    df = pd.read_csv(path, usecols=['timestamp','open','high','low','close'],
                     index_col='timestamp', parse_dates=True)
    if getattr(df.index, 'tz', None) is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def resample_tf(df1m, tf_min):
    return df1m.resample(f"{tf_min}min", label='left', closed='left').agg(
        {'open':'first','high':'max','low':'min','close':'last'}).dropna()


def rma(x, n):
    a = np.asarray(x, float); out = np.full(len(a), np.nan)
    if len(a) < n: return out
    out[n-1] = a[:n].mean()
    for i in range(n, len(a)):
        out[i] = (out[i-1]*(n-1)+a[i])/n
    return out


def compute_rsi(close, n):
    c = np.asarray(close, float); d = np.diff(c, prepend=c[0])
    ag = rma(np.where(d>0,d,0.0), n); al = rma(np.where(d<0,-d,0.0), n)
    rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al>0)
    rsi = 100 - 100/(1+rs); rsi[al==0] = 100.0
    return rsi


def compute_atr(high, low, close, n):
    h=np.asarray(high,float); l=np.asarray(low,float); c=np.asarray(close,float)
    pc=np.roll(c,1); pc[0]=c[0]
    tr=np.maximum.reduce([h-l,np.abs(h-pc),np.abs(l-pc)])
    return rma(tr, n)


def compute_dmi(high, low, close, n, smooth):
    h=np.asarray(high,float); l=np.asarray(low,float); c=np.asarray(close,float)
    up=h-np.roll(h,1); dn=np.roll(l,1)-l; up[0]=0; dn[0]=0
    pdm=np.where((up>dn)&(up>0),up,0.0); ndm=np.where((dn>up)&(dn>0),dn,0.0)
    pc=np.roll(c,1); pc[0]=c[0]
    tr=np.maximum.reduce([h-l,np.abs(h-pc),np.abs(l-pc)])
    atr=rma(tr,n)
    pdi=100*rma(pdm,n)/np.where(atr>0,atr,np.nan)
    ndi=100*rma(ndm,n)/np.where(atr>0,atr,np.nan)
    dx=100*np.abs(pdi-ndi)/np.where((pdi+ndi)>0,pdi+ndi,np.nan)
    return rma(np.nan_to_num(dx), smooth)


def pivots(high, low, L, R):
    h=np.asarray(high,float); l=np.asarray(low,float); n=len(h)
    ph_at={}; pl_at={}
    for c in range(L, n-R):
        sh=h[c-L:c+R+1]; sl=l[c-L:c+R+1]
        if h[c]==sh.max() and (sh==h[c]).sum()==1: ph_at[c+R]=float(h[c])
        if l[c]==sl.min() and (sl==l[c]).sum()==1: pl_at[c+R]=float(l[c])
    return ph_at, pl_at


def precompute(df):
    high=df['high'].values; low=df['low'].values; close=df['close'].values; open_=df['open'].values; n=len(close)
    rsi=compute_rsi(close,RSI_LEN); atr=compute_atr(high,low,close,ATR_LEN); adx=compute_dmi(high,low,close,ADX_LEN,ADX_SMOOTH)
    ph_at,pl_at=pivots(high,low,PIV_L,PIV_R)
    years=df.index.year.values
    months=np.array([f"{df.index[i].year}-{df.index[i].month:02d}" for i in range(n)])
    return {'high':high,'low':low,'close':close,'open':open_,'n':n,'rsi':rsi,'atr':atr,'adx':adx,
            'ph_at':ph_at,'pl_at':pl_at,'years':years,'months':months}


def sl_update(mode, side, pb, lastPH, lastPL, piv, prevSL, entry):
    # ★SL 어댑터: A_STEP(단계 가변비율) 또는 FIXxx(고정위치). 비가역(롱max/숏min)+폴백 보장.
    if side == 1:                       # 롱: 고점 lastPH, 새저점 piv
        span = lastPH - piv
        if mode == 'A_STEP':
            ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            cand = lastPH - ratio * span      # 고점기준(원본 A안)
        else:
            p = FIX_POS[mode]
            cand = piv + p * span             # 눌림목+p위치 (고정)
        sl = cand if np.isnan(prevSL) else max(prevSL, cand)
        disaster = entry * (1 - BAL_SL/100.0)
        if not np.isfinite(sl): sl = disaster          # 폴백
        return max(sl, disaster)                       # 재난선 아래로는 안감
    else:                               # 숏: 저점 lastPL, 새고점 piv
        span = piv - lastPL
        if mode == 'A_STEP':
            ratio = FIB[0] if pb == 1 else FIB[1] if pb == 2 else FIB[2]
            cand = lastPL + ratio * span      # 저점기준(원본 A안)
        else:
            p = FIX_POS[mode]
            cand = piv - p * span             # 고점-p위치 (고정, 거울상)
        sl = cand if np.isnan(prevSL) else min(prevSL, cand)
        disaster = entry * (1 + BAL_SL/100.0)
        if not np.isfinite(sl): sl = disaster
        return min(sl, disaster)


def scen_label(adx_i, structUp, structDn, adx_th_ref=22):
    strong = (not np.isnan(adx_i)) and adx_i >= adx_th_ref
    if structUp and strong:  return 'strong_breakout'
    if structUp:             return 'clean_uptrend'
    if structDn and strong:  return 'high_adx'
    if structDn:             return 'clean_downtrend'
    if strong:               return 'v_reversal'
    return 'choppy_range' if (np.isnan(adx_i) or adx_i < 18) else 'low_adx'


def run_bot(df, sig, par):
    high=sig['high']; low=sig['low']; close=sig['close']; open_=sig['open']; n=sig['n']
    rsi=sig['rsi']; atr=sig['atr']; adx=sig['adx']; ph_at=sig['ph_at']; pl_at=sig['pl_at']
    months=sig['months']; years=sig['years']
    rsiOS=par['rsiOS']; rsiOSs=par['rsiOSs']; gate_mode=par['gate']; adx_th=par['adx_th']
    direction=par['dir']; sl_mode=par['sl_mode']
    allow_long = direction in ('LONG','BOTH'); allow_short = direction in ('SHORT','BOTH')

    lastPH=np.nan; prevPH=np.nan; lastPL=np.nan; prevPL=np.nan
    pos=0; avg=np.nan; entry_i=-1; pb=0; trailSL=np.nan
    waiting_L=False; waitBars_L=0; waiting_S=False; waitBars_S=0; scen0=None
    trades=[]

    for i in range(n):
        new_ph = i in ph_at; new_pl = i in pl_at
        ph_i = ph_at.get(i, np.nan); pl_i = pl_at.get(i, np.nan)
        if new_ph: prevPH=lastPH; lastPH=ph_i
        if new_pl: prevPL=lastPL; lastPL=pl_i
        structUp = (not np.isnan(lastPH)) and (not np.isnan(prevPH)) and lastPH>prevPH
        structDn = (not np.isnan(lastPL)) and (not np.isnan(prevPL)) and lastPL<prevPL
        gate = True if gate_mode=='OFF' else ((not np.isnan(adx[i])) and adx[i]>adx_th)

        if pos != 0:
            if pos==1 and new_pl and not np.isnan(lastPH):
                pb += 1
                trailSL = sl_update(sl_mode, 1, pb, lastPH, lastPL, pl_i, trailSL, avg)
            elif pos==-1 and new_ph and not np.isnan(lastPL):
                pb += 1
                trailSL = sl_update(sl_mode, -1, pb, lastPH, lastPL, ph_i, trailSL, avg)

            bars_in = i - entry_i; exit_px=np.nan; reason=None
            if pos==1:
                balStop = avg*(1-BAL_SL/100.0)
                stopUse = balStop if np.isnan(trailSL) else max(trailSL, balStop)
                if bars_in>=TIME_STOP: exit_px=close[i]; reason='time'
                elif low[i]<=stopUse:  exit_px=stopUse; reason='trail_sl'
            else:
                balStop = avg*(1+BAL_SL/100.0)
                stopUse = balStop if np.isnan(trailSL) else min(trailSL, balStop)
                if bars_in>=TIME_STOP: exit_px=close[i]; reason='time'
                elif high[i]>=stopUse: exit_px=stopUse; reason='trail_sl'
            if reason is not None:
                gross = (exit_px-avg)/avg if pos==1 else (avg-exit_px)/avg
                R = gross - COMMISSION*2
                trades.append({'side':pos,'entry_t':df.index[entry_i],'exit_t':df.index[i],
                               'entry':avg,'exit':exit_px,'R':R,'reason':reason,'bars':bars_in,
                               'scen':scen0,'year':years[i],'month':months[i]})
                pos=0; avg=np.nan; pb=0; trailSL=np.nan
            continue

        if allow_long:
            setup_L = structUp and gate and new_pl and (not np.isnan(lastPH))
            if setup_L and not waiting_L: waiting_L=True; waitBars_L=0
            if waiting_L: waitBars_L += 1
            trigL = (rsi[i-1] <= rsiOS < rsi[i]) if i>0 else False
            if waiting_L and trigL:
                px = open_[i+1] if i+1<n else close[i]
                pos=1; avg=px; entry_i=i; pb=0; trailSL=px*(1-SLPCT/100.0)
                scen0=scen_label(adx[i],structUp,structDn); waiting_L=False; waitBars_L=0; waiting_S=False
                continue
            if waiting_L and waitBars_L>WAIT_MAX: waiting_L=False; waitBars_L=0

        if allow_short and pos==0:
            setup_S = structDn and gate and new_ph and (not np.isnan(lastPL))
            if setup_S and not waiting_S: waiting_S=True; waitBars_S=0
            if waiting_S: waitBars_S += 1
            trigS = (rsi[i-1] >= rsiOSs > rsi[i]) if i>0 else False
            if waiting_S and trigS:
                px = open_[i+1] if i+1<n else close[i]
                pos=-1; avg=px; entry_i=i; pb=0; trailSL=px*(1+SLPCT/100.0)
                scen0=scen_label(adx[i],structUp,structDn); waiting_S=False; waitBars_S=0; waiting_L=False
                continue
            if waiting_S and waitBars_S>WAIT_MAX: waiting_S=False; waitBars_S=0

    return trades


def agg(trades, years=None, side_filter=None):
    if years is not None: trades=[t for t in trades if t['year'] in years]
    if side_filter is not None: trades=[t for t in trades if t['side']==side_filter]
    if not trades:
        return {'trades':0,'win_pct':0.0,'cumR_pct':0.0,'PF':0.0,'payoff':0.0,'final_cap':START_CAP}
    R=np.array([t['R'] for t in trades]); wins=R[R>0]; losses=R[R<0]
    gp=wins.sum(); gl=-losses.sum(); pf=(gp/gl) if gl>0 else 999.0
    payoff=(wins.mean()/-losses.mean()) if (len(wins) and len(losses)) else 0.0
    cap=START_CAP
    for r in R: cap*=(1+r)
    return {'trades':len(trades),'win_pct':round(len(wins)/len(trades)*100,1),
            'cumR_pct':round(R.sum()*100,2),'PF':round(pf,3),
            'payoff':round(payoff,3),'final_cap':round(float(cap),2)}


def monthly(trades, side_filter):
    sub=[t for t in trades if t['side']==side_filter]; out={}
    for t in sub: out.setdefault(t['month'],[]).append(t['R'])
    rows=[]
    for m in sorted(out.keys()):
        R=np.array(out[m]); wins=R[R>0]; losses=R[R<0]; gl=-losses.sum()
        cap=START_CAP
        for r in R: cap*=(1+r)
        rows.append({'month':m,'side':'LONG' if side_filter==1 else 'SHORT','trades':len(R),
                     'win_pct':round(len(wins)/len(R)*100,1),'cumR_pct':round(R.sum()*100,2),
                     'PF':round((wins.sum()/gl) if gl>0 else 999.0,3),
                     'payoff':round((wins.mean()/-losses.mean()) if (len(wins) and len(losses)) else 0.0,3),
                     'pnl_usd':round(float(cap-START_CAP),2)})
    return rows


def pick_best(runs, sl_mode):
    best_both=None; best_any=None
    for r in runs:
        if r['sl_mode']!=sl_mode: continue
        if r['tr_trades']>=15:
            if best_any is None or r['tr_PF']>best_any['tr_PF']: best_any=r
            if r['dir']=='BOTH' and (best_both is None or r['tr_PF']>best_both['tr_PF']): best_both=r
    return best_both if best_both is not None else best_any


def main():
    print("[05Alpha_Up_Ch1_SLpos_stg3] SL 위치 스윕(A_STEP + FIX 0.2~0.8) 롱숏 비교")
    data=find_data(); print(f"[data] {data}")
    df1m=load_1m(data); print(f"[load] {len(df1m):,}rows | {df1m.index.min().date()}~{df1m.index.max().date()}")

    sig_cache={}
    for tf in GRID_TF:
        dd=resample_tf(df1m,tf); sig_cache[tf]=(dd, precompute(dd))
        print(f"[tf {tf//60}h] {len(dd)} bars")

    combos=[]
    for tf in GRID_TF:
        for rsiOS in GRID_rsiOS:
            for rsiOSs in GRID_rsiOSs:
                for gate in GRID_gate:
                    for ath in (GRID_adxTh if gate=='ADX_TREND' else [GRID_adxTh[0]]):
                        for direction in GRID_dir:
                            for sl_mode in GRID_SLMODE:
                                combos.append((tf,rsiOS,rsiOSs,gate,ath,direction,sl_mode))
    print(f"[grid] {len(combos)} runs")

    summary_runs=[]; trades_by_key={}; done=0
    for (tf,rsiOS,rsiOSs,gate,ath,direction,sl_mode) in combos:
        dd,sig=sig_cache[tf]
        par={'rsiOS':rsiOS,'rsiOSs':rsiOSs,'gate':gate,'adx_th':ath,'dir':direction,'sl_mode':sl_mode}
        trades=run_bot(dd,sig,par)
        lab=f"TF{tf//60}h_osL{rsiOS}_osS{rsiOSs}_{gate}_adx{ath}_{direction}"
        mTr=agg(trades,TRAIN_YEARS); mTe=agg(trades,TEST_YEARS)
        summary_runs.append({'sl_mode':sl_mode,'cell':lab,'TF_h':tf//60,'rsiOS':rsiOS,'rsiOSs':rsiOSs,
                             'gate':gate,'adx_th':ath,'dir':direction,
                             'tr_trades':mTr['trades'],'tr_PF':mTr['PF'],'tr_cumR':mTr['cumR_pct'],
                             'te_trades':mTe['trades'],'te_PF':mTe['PF'],'te_cumR':mTe['cumR_pct']})
        trades_by_key[(sl_mode,lab)]=trades; done+=1
        if done % 200 == 0: print(f"[progress] {done}/{len(combos)}")

    # SL모드별 best + 롱숏분해 + 월별 + 시나리오
    verdict_lines=[]; best_meta={}; scen_rows=[]; monthly_rows=[]
    pos_summary=[]   # 위치별 평균 test PF (롱/숏 따로)
    for sl_mode in GRID_SLMODE:
        b=pick_best(summary_runs, sl_mode)
        if b is None:
            verdict_lines.append(f"{sl_mode}: 표본부족"); best_meta[sl_mode]=None
            for s in SCEN: scen_rows.append({'sl_mode':sl_mode,'scen':s,'n':0,'cumR':0})
            continue
        bt=trades_by_key[(sl_mode,b['cell'])]
        m_tr=agg(bt,TRAIN_YEARS); m_te=agg(bt,TEST_YEARS)
        wfe=round((m_te['PF']/m_tr['PF'])*100,1) if m_tr['PF']>0 else 0
        L=agg(bt,None,1); S=agg(bt,None,-1)
        verdict_lines.append(
            f"{sl_mode} BEST[{b['cell']}] trainPF={m_tr['PF']} testPF={m_te['PF']} WFE={wfe}% "
            f"|| L n{L['trades']} 승{L['win_pct']}% R{L['cumR_pct']}% PF{L['PF']} 손익비{L['payoff']} ${L['final_cap']-START_CAP:.0f} "
            f"|| S n{S['trades']} 승{S['win_pct']}% R{S['cumR_pct']}% PF{S['PF']} 손익비{S['payoff']} ${S['final_cap']-START_CAP:.0f}")
        best_meta[sl_mode]={'b':b,'bt':bt,'L':L,'S':S}
        for s in SCEN:
            rs=[t['R'] for t in bt if t['scen']==s]
            scen_rows.append({'sl_mode':sl_mode,'scen':s,'n':len(rs),'cumR':round(float(np.sum(rs))*100,2) if rs else 0.0})
        for row in monthly(bt,1)+monthly(bt,-1):
            row['sl_mode']=sl_mode; monthly_rows.append(row)
        # 위치별: 같은 방향 모든 런 평균 (롱/숏 따로) — 위치 효과를 평균으로 본다
        for dr,sd in [('LONG',1),('SHORT',-1)]:
            runs_dir=[r for r in summary_runs if r['sl_mode']==sl_mode and r['dir']==dr and r['te_trades']>=15]
            if runs_dir:
                pos_summary.append({'sl_mode':sl_mode,'side':dr,'runs':len(runs_dir),
                                    'avg_test_PF':round(float(np.mean([r['te_PF'] for r in runs_dir])),3),
                                    'avg_test_cumR':round(float(np.mean([r['te_cumR'] for r in runs_dir])),2),
                                    'pf_gt1_pct':round(float(np.mean([r['te_PF']>1 for r in runs_dir]))*100,0)})

    # 최종 결론: A_STEP vs 최고 FIX
    fixmodes=[m for m in GRID_SLMODE if m!='A_STEP' and best_meta.get(m)]
    a=best_meta.get('A_STEP')
    if a and fixmodes:
        bestfix=max(fixmodes, key=lambda m:best_meta[m]['b']['te_PF'])
        af=best_meta[bestfix]['b']['te_PF']; aa=a['b']['te_PF']
        if af>aa: concl=f"최고고정 {bestfix}(testPF {af}) > A_STEP({aa}) -> 고정SL 우위, 알파상승"
        elif aa>af: concl=f"A_STEP(testPF {aa}) > 최고고정 {bestfix}({af}) -> 단계형 유지"
        else: concl=f"A_STEP=최고고정 {bestfix} 동률({aa})"
    else:
        concl="표본부족"
    verdict="VERDICT: "+concl+" || "+" || ".join(verdict_lines)
    print("[verdict] "+verdict)

    pd.DataFrame([{'cell':verdict}]+summary_runs).to_csv(os.path.join(HERE,"sl_summary.csv"),index=False,encoding='utf-8-sig')
    # 위치 스윕 요약을 summary 뒤에 별도 저장
    pd.DataFrame(pos_summary).to_csv(os.path.join(HERE,"sl_position_sweep.csv"),index=False,encoding='utf-8-sig')

    all_td=[]
    for sl_mode in GRID_SLMODE:
        meta=best_meta.get(sl_mode)
        if not meta: continue
        for t in meta['bt']:
            all_td.append({'sl_mode':sl_mode,'side':'LONG' if t['side']==1 else 'SHORT',
                           'entry_t':t['entry_t'].strftime('%Y-%m-%d %H:%M'),'exit_t':t['exit_t'].strftime('%Y-%m-%d %H:%M'),
                           'year':t['year'],'month':t['month'],'entry':round(t['entry'],2),'exit':round(t['exit'],2),
                           'R_pct':round(t['R']*100,4),'reason':t['reason'],'bars':t['bars'],'scen':t['scen']})
    cols_td=['sl_mode','side','entry_t','exit_t','year','month','entry','exit','R_pct','reason','bars','scen']
    (pd.DataFrame(all_td) if all_td else pd.DataFrame(columns=cols_td)).to_csv(os.path.join(HERE,"sl_trades.csv"),index=False,encoding='utf-8-sig')

    cols_m=['sl_mode','month','side','trades','win_pct','cumR_pct','PF','payoff','pnl_usd']
    (pd.DataFrame(monthly_rows)[cols_m] if monthly_rows else pd.DataFrame(columns=cols_m)).to_csv(os.path.join(HERE,"sl_monthly.csv"),index=False,encoding='utf-8-sig')

    if not scen_rows:
        scen_rows=[{'sl_mode':m,'scen':s,'n':0,'cumR':0} for m in GRID_SLMODE for s in SCEN]
    pd.DataFrame(scen_rows).to_csv(os.path.join(HERE,"sl_scenarios.csv"),index=False,encoding='utf-8-sig')
    print("[save] sl_summary / sl_position_sweep / sl_trades / sl_monthly / sl_scenarios .csv")


if __name__ == "__main__":
    main()
