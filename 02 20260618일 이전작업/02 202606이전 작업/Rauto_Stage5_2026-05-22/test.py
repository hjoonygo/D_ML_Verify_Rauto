# -*- coding: utf-8 -*-
# [파일명] test.py  (Stage2 MTF)
# 코드길이: 약 330줄, 내부버전명: Stage5_mtf_wait_fibgrid, 로직 축약/생략 없이 전체 출력
#
# [목적] OB+SL/TP를 상위TF(5/15/60분)에서 잡고 청산은 1분봉. (보고서 df_ob_tf 설계)
#   1분봉 한계(1차OB 0.08% 코앞, 게이트통과 0.06%)를 상위TF로 해소되는지 검증.
#   ★사용자 강조: OB의 SL/TP 평균거리 + 없는 경우(%) + 게이트통과율을 TF별 진단표로 먼저 측정.
#   부품(게이트·계단익절·0.382피보락인·위험7%복리·강제청산)은 Stage1e 그대로 재사용.
#
# [그리드] OB TF {5, 15, 60분} 비교. RR_MIN=3.0 고정. SL 3안(원래OB SL). 락인0.382.
#
# [진입] '진입신호 자체는 비중요'(사용자) -> 하락장 봉마다 후보, 게이트 통과시 진입.
#   단 상위TF OB라 진입 간격을 상위TF봉 단위로(빈구간 점프) -> 속도가속.
#
# [★결과 전량 파일] S5_diag_*.csv(진단) + S5_trades_*.csv + S5_summary.csv. 복붙 불필요.
# [경로] 하위폴더 실행, 데이터 상위 D:\ML\verify. check.py가 ..\00WorkHstr\.
#
# [함수 In/Out]
#   load_data / resample_tf / precompute_tf_pivots (ob_mtf)
#   entry_gate_mtf(price,ts,...) -> dict(pass,sl_price,tp_price,sl_dist,tp_dist,rr,fail)
#   diagnose(...) -> TF별 OB 거리/없음%/게이트통과율 (진단표)
#   simulate_one(...) -> 거래행 (Exec_Fibo_v3 청산, 복리위험7%)
#   run_tf(...) -> 거래 + 자본곡선 + 진단
# ==============================================================================

import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from ob_mtf import resample_tf, precompute_tf_pivots, nearest_above_mtf, nearest_below_mtf
from Exec_Fibo_v3 import Exec_Fibo_v3  # 1차익절50%+LH-LL락인

SL_GATE = 0.0032; TP_GATE = 0.0048; SL_CLAMP = 0.0100; TP_CLAMP = 0.01618
RR_MIN = 1.5
WAIT_MIN = 240          # 대기 진입 4시간
LEVERAGE = 5; START_CAP = 10000.0; RISK_PCT = 0.07; LIQ_MOVE = 0.20
COST = 0.0004; FUNDING_DAILY = 0.0001; MIN_CAP = 100.0
W_TF = 3                  # 상위TF pivot 윈도우(좌우 3봉)
REGIME_COL = 'feat_struct_8'
MAX_HOLD_BARS = 60*24*120
OB_TF = 60               # OB TF 고정(Stage2서 60분이 SL/통과율 best)
FIB_LIST = [0.618, 0.5, 0.382]   # Fib 락인 비율 3개 비교


def find_data():
    for d in [PARENT, HERE, r"D:\ML\verify", r"D:\ML\Verify"]:
        for n in ["Merged_Data_with_Regime_Features.csv", "Merged_Data.csv"]:
            p = os.path.join(d, n)
            if os.path.exists(p): return p
    raise FileNotFoundError("상위 D:\\ML\\verify 데이터 필요")


def load_data(path):
    head = pd.read_csv(path, nrows=1)
    cols = ['timestamp','open','high','low','close']
    if REGIME_COL not in head.columns: raise KeyError(f"{REGIME_COL} 없음")
    cols.append(REGIME_COL)
    df = pd.read_csv(path, usecols=cols, index_col='timestamp', parse_dates=True)
    if getattr(df.index,'tz',None) is not None: df.index = df.index.tz_localize(None)
    return df.sort_index()


def entry_gate_mtf(price, ts, hpc, hpt, hpb, lpc, lpt, lpb):
    """상위TF OB로 게이트. 숏: TP=아래지지OB, SL=위저항OB."""
    res = {'pass':False,'fail':None,'sl_price':None,'tp_price':None,'sl_dist':None,'tp_dist':None,'rr':None}
    tp = nearest_below_mtf(price, ts, lpc, lpt, lpb)   # 지지OB
    sl = nearest_above_mtf(price, ts, hpc, hpt, hpb)   # 저항OB
    if tp is None: res['fail']='no_tp_ob'; return res
    tp_price=tp[0]; tp_dist=(price-tp_price)/price
    res['tp_price']=tp_price; res['tp_dist']=tp_dist
    if sl is None: res['fail']='no_sl_ob'; return res
    sl_price=sl[0]; sl_dist=(sl_price-price)/price
    res['sl_price']=sl_price; res['sl_dist']=sl_dist
    if sl_dist < SL_GATE: res['fail']='sl_gate'; return res
    if sl_dist > SL_CLAMP: sl_eff=SL_CLAMP; tp_req=TP_CLAMP
    else: sl_eff=sl_dist; tp_req=TP_GATE
    res['sl_dist']=sl_eff
    if tp_dist < tp_req: res['fail']='tp_gate'; return res
    rr=tp_dist/max(sl_eff,1e-8); res['rr']=rr
    if rr < RR_MIN: res['fail']='rr_gate'; return res
    res['pass']=True
    return res


def simulate_one(exec_eng, df, o,h,l,c, idx, e_idx, gate, capital, fib_ext):
    entry=c[e_idx]; sl_dist=gate['sl_dist']
    risk_amt=capital*RISK_PCT
    notional=min(risk_amt/sl_dist, capital*2)
    liq_price=entry*(1+LIQ_MOVE)
    bs={'position':'SHORT','entry_price':entry,'remaining_pct':1.0,'target_idx':0,'ob_initialized':True,
        'fib_wave_start':entry,'fib_extreme':entry,'pulled_back':False,'fib_stop':None,
        'bullish_obs':[{'top':gate['tp_price']*1.0002,'bottom':gate['tp_price'],'mean':gate['tp_price']}],
        'bearish_obs':[],'entry_regime':'downtrend','entry_reason':'gate',
        'init_sl_price':gate['sl_price'],'lh_price':entry,'floor_init':None,'reduced_once':False}
    first_i=e_idx+1; w0=max(0,first_i-60+1)
    bs['df_1m']=df.iloc[w0:first_i+1]
    params={'leverage':LEVERAGE,'fib_trigger_roe':15.0,'fib_sl_roe':3.0,'innovation1':True,'sl_mode':3,'fib_ext_pct':fib_ext}
    size=notional; reduced=False; pnl_total=0.0
    n=len(c); end_idx=min(n,e_idx+1+MAX_HOLD_BARS); rows=[]
    for i in range(e_idx+1,end_idx):
        o_,h_,l_,c_=o[i],h[i],l[i],c[i]
        ticks=(o_,h_,l_,c_) if c_<o_ else (o_,l_,h_,c_)
        for price in ticks:
            if price>=liq_price:
                loss=size*((entry-liq_price)/entry); fee=size*COST*2
                pnl_total+=loss-fee
                rows.append(_row(entry,liq_price,size,idx[e_idx],idx[i],reduced,'강제청산(-20%)',loss-fee))
                return rows,pnl_total,'강제청산'
            sig=exec_eng.check_exit(price,bs,params); act=sig.get('action') if sig else None
            if act=='REDUCE_SHORT' and not reduced:
                amt=size*0.5; pnl=amt*((entry-price)/entry); fee=amt*COST*2
                pnl_total+=pnl-fee
                rows.append(_row(entry,price,amt,idx[e_idx],idx[i],False,'1차OB분할익절',pnl-fee))
                size*=0.5; reduced=True; continue
            if act=='CLOSE_SHORT':
                pnl=size*((entry-price)/entry); fee=size*COST*2
                dur=(idx[i]-idx[e_idx]).total_seconds()/86400; funding=size*FUNDING_DAILY*dur
                pnl_total+=pnl-fee-funding
                rows.append(_row(entry,price,size,idx[e_idx],idx[i],reduced,sig['reason'][:30],pnl-fee-funding))
                return rows,pnl_total,'close'
        if (i-e_idx)>=240 and not reduced:
            price=c_; pnl=size*((entry-price)/entry); fee=size*COST*2
            pnl_total+=pnl-fee
            rows.append(_row(entry,price,size,idx[e_idx],idx[i],reduced,'timeout_4h',pnl-fee))
            return rows,pnl_total,'timeout'
    price=c[end_idx-1]; pnl=size*((entry-price)/entry); pnl_total+=pnl-size*COST*2
    rows.append(_row(entry,price,size,idx[e_idx],idx[end_idx-1],reduced,'max_hold',pnl))
    return rows,pnl_total,'max_hold'


def _row(entry,price,size,et,xt,reduced,reason,net):
    return dict(진입시간=et.strftime('%Y-%m-%d %H:%M:%S'),청산시간=xt.strftime('%Y-%m-%d %H:%M:%S'),
                연도=et.year,진입가=round(entry,2),청산가=round(price,2),명목=round(size,2),
                청산사유=reason,순수익=round(net,2),구분='REDUCE' if '분할' in reason else 'CLOSE')


def wait_entry(c, idx, t0, hpc,hpt,hpb, lpc,lpt,lpb, diag):
    """단순 대기 진입: t0 게이트검사. 미달이면 4h 매분 재검사, 통과시 그 시점 진입.
       반환 (e_idx, gate) 통과 / (None,사유). OB는 매분 새로 보되 게이트3조건 충족시 진입."""
    g = entry_gate_mtf(c[t0], idx[t0], hpc,hpt,hpb, lpc,lpt,lpb)
    diag['checked']+=1
    if g['sl_dist'] is not None: diag['sl_dist'].append(g['sl_dist'])
    if g['tp_dist'] is not None: diag['tp_dist'].append(g['tp_dist'])
    if g['rr'] is not None: diag['rr'].append(g['rr'])
    if g['pass']:
        return t0, g
    for k in range(1, WAIT_MIN+1):
        t=t0+k
        if t>=len(c): return None,'wait_no_data'
        g=entry_gate_mtf(c[t], idx[t], hpc,hpt,hpb, lpc,lpt,lpb)
        if g['pass']:
            diag['wait_success']+=1
            return t, g
    diag['wait_timeout']+=1
    return None,'wait_timeout'


def run_tf(df, o,h,l,c, idx, down_idx, fib_ext):
    df_tf=resample_tf(df, OB_TF)
    hpc,lpc,hpt,hpb,lpt,lpb = precompute_tf_pivots(df_tf, W_TF, OB_TF)
    exec_eng=Exec_Fibo_v3()
    cap=START_CAP; cap_curve=[cap]; trades=[]; bankrupt=False
    diag={'sl_dist':[], 'tp_dist':[], 'rr':[], 'pass':0, 'checked':0,
          'wait_success':0, 'wait_timeout':0, 'fib_cnt':0}
    n=len(c); cur=0
    dptr=np.searchsorted(down_idx, cur, side='left')
    while dptr<len(down_idx):
        t0=int(down_idx[dptr])
        if t0>=n-1: break
        if cap<=MIN_CAP: bankrupt=True; break
        e_idx, gate = wait_entry(c, idx, t0, hpc,hpt,hpb, lpc,lpt,lpb, diag)
        if e_idx is not None:
            diag['pass']+=1
            rows,pnl,why=simulate_one(exec_eng, df, o,h,l,c, idx, e_idx, gate, cap, fib_ext)
            if any('Fibonacci' in str(r['청산사유']) or '락인' in str(r['청산사유']) for r in rows):
                diag['fib_cnt']+=1
            cap+=pnl; cap_curve.append(cap)
            for r in rows: r['거래후자본']=round(cap,2)
            trades.extend(rows)
            last_x=pd.to_datetime(rows[-1]['청산시간']); x_idx=idx.searchsorted(last_x)
            cur=max(int(x_idx)+1,e_idx+1)
        else:
            cur=t0+OB_TF    # 상위TF 간격 점프(속도가속)
        dptr=np.searchsorted(down_idx,cur,side='left')
    return trades, cap_curve, bankrupt, diag


def main():
    print("[Stage5] Stage2-MTF base + 대기진입4h + 1차익절50% + Fib락인{0.618,0.5,0.382} 비교")
    data=find_data(); print(f"[데이터] {data}")
    df=load_data(data)
    o,h,l,c=df['open'].values,df['high'].values,df['low'].values,df['close'].values
    idx=df.index
    down_idx=np.where(df[REGIME_COL].astype(str).values=='downtrend')[0]
    print(f"[로드] {len(df):,}행 하락장 {len(down_idx):,}봉. OB TF {OB_TF}분 고정. Fib {FIB_LIST} 비교...\n")

    summary=[]; diag_rows=[]
    for fib in FIB_LIST:
        trades,curve,bankrupt,diag=run_tf(df,o,h,l,c,idx,down_idx,fib)
        tag=f"fib{int(fib*1000)}"
        pd.DataFrame(trades).to_csv(os.path.join(HERE,f"S5_trades_{tag}.csv"),index=False,encoding='utf-8-sig')
        curve=np.array(curve)
        sl=np.array(diag['sl_dist']); tp=np.array(diag['tp_dist']); rr=np.array(diag['rr'])
        dg=dict(Fib=fib, 검사수=diag['checked'], 진입=diag['pass'], 대기성공=diag['wait_success'],
                대기타임아웃=diag['wait_timeout'], 피보발동=diag['fib_cnt'],
                SL중앙bp=round(np.median(sl)*10000,1) if len(sl) else 0,
                TP중앙bp=round(np.median(tp)*10000,1) if len(tp) else 0,
                RR중앙=round(np.median(rr),2) if len(rr) else 0)
        diag_rows.append(dg)
        if len(trades):
            d=pd.DataFrame(trades); g=d.groupby('진입시간')['순수익'].sum().values
            pf=g[g>0].sum()/abs(g[g<0].sum()) if (g<0).any() else 9.99
            mdd=(curve-np.maximum.accumulate(curve)).min()
            row=dict(Fib=fib,진입수=len(g),PF=round(pf,3),승률=round((g>0).mean()*100,1),
                     최종자본=round(curve[-1]),수익률=f"{(curve[-1]/START_CAP-1)*100:.0f}%",
                     최저자본=round(curve.min()),MDD=round(mdd),파산='YES' if bankrupt else 'NO')
        else:
            row=dict(Fib=fib,진입수=0,PF=0,승률=0,최종자본=int(START_CAP),수익률='0%',
                     최저자본=int(START_CAP),MDD=0,파산='NO')
        summary.append(row)
        print(f"  [Fib{fib}] 진입{row['진입수']} (대기성공{dg['대기성공']}) 피보발동{dg['피보발동']} "
              f"SL{dg['SL중앙bp']}bp TP{dg['TP중앙bp']}bp -> PF={row['PF']} 자본{row['수익률']} 파산{row['파산']}")

    pd.DataFrame(diag_rows).to_csv(os.path.join(HERE,"S5_diag.csv"),index=False,encoding='utf-8-sig')
    pd.DataFrame(summary).to_csv(os.path.join(HERE,"S5_summary.csv"),index=False,encoding='utf-8-sig')
    print("\n[저장] S5_diag.csv + S5_trades_*.csv + S5_summary.csv — 전량 파일")
    print("[1차확인] 대기진입으로 진입수 적정화 + Fib비율별 피보발동/PF 비교")


if __name__=="__main__":
    main()
