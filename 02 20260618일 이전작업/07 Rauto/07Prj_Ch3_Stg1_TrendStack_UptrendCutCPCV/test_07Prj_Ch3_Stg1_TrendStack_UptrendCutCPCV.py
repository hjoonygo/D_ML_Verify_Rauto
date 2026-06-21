# [파일명] test_07Prj_Ch3_Stg1_TrendStack_UptrendCutCPCV.py
# 코드길이: 약 235줄 / 내부버전: build_ch3s1_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 추세봇 TrendStack 264거래에 'uptrend(실시간 feat_struct) 진입수량 0.3배' 단일룰을 적용해,
#        그 효과(수익·MDD·Calmar)가 과거 4년 폴드마다 견고한지(특히 2024 강세해 생존) 측정한다.
#        - 기준선 = OPVnN(반대진입 0.6배) 적용 복리엔진 (Stg6에서 +585%/MDD-20.1% 검증됨)
#        - 룰     = 기준선 mult 에 'feat_struct==uptrend 면 ×0.3' 한 줄만 추가
#        파라미터(0.3·OPV·n·N) 동시최적화는 2순위. 이번 1순위는 0.3 '고정 단일룰'의 견고성만 본다.
#
# [미래참조 차단] feat_struct_8 은 진입봉(7h) 닫힘 시점 entry_t '이하' 최근값으로 asof(backward).
#                label_smc_8 은 비교/검증용으로만 읽고 룰엔 절대 미사용. shift(-) 없음.
#
# [속도 최적화] ①복리/낙폭을 numpy 배열 루프로(iterrows 제거) ②feat asof 는 usecols+단일 searchsorted
#              ③feat 결과를 _featcache.csv 로 캐시(다음 실행은 698MB 재파싱 생략) ④CPCV 는 고정룰이라
#              학습이 없음 → 폴드당 1회 복리만(파라미터 적합 루프 없음).
#
# ── 사용 파일 (상위 D:\ML\verify 자동탐지, 하위폴더 실행 기준 '..' 우선) ──────────────
#  IN  stg6_levsweep_ledger.csv               : 원장 entry_t,exit_t,side,R,fund,mae,year (복리 원천)
#  IN  *OPVnN*devledger*.csv                  : entry_t,dev,regime_dir (OPVnN mult용)
#  IN  Merged_Data_with_Regime_Features.csv   : timestamp,feat_struct_8 (실시간 장세; 폴백: 이전 *joined.csv 의 feat)
#  OUT (cwd 저장) <BASE>_summary.csv  : 기준선 vs 룰 전체성과 + 2024 효과 한 줄 요약
#  OUT (cwd 저장) <BASE>_cpcv.csv     : 블록 CPCV 조합별 OOS Δ(수익·MDD·Calmar) 분포
#  OUT (cwd 저장) <BASE>_yearly.csv   : 연도 폴드별 기준선 vs 룰 + 워크포워드
#  OUT (cwd 저장) <BASE>_featcache.csv: feat asof 캐시 (재실행 가속)
#
# ── 함수 (In/Out) ───────────────────────────────────────────────────────
#  find_in_tree(cands)       In: 후보명 list           Out: 경로 str|None (..·.·절대 자동탐지)
#  _naive(s)                 In: 시각 Series            Out: tz 제거 naive datetime
#  load_join()               In: -                      Out: (DataFrame[entry_t,side,R,fund,mae,year,m_base], 출처str)
#  load_feat(entry_t, base)  In: 진입시각 ndarray·BASE   Out: (feat_struct ndarray, 출처str)  ※asof backward
#  compound(R,mae,fund,mult) In: 거래 배열 4종(시간정렬) Out: (잔액,수익%,MDD%,Calmar)  ← 검증엔진 + 낙폭추적
#  metrics(df, mcol)         In: 거래df·mult컬럼명       Out: (수익%,MDD%,Calmar)
#  make_blocks(n, k_list)    In: 거래수·k리스트          Out: 블록경계 + OOS 조합 인덱스 list (퍼지 적용)
#  block_cpcv(df)            In: 거래df(정렬)            Out: 조합별 Δ DataFrame + 요약 dict
#  walk_forward(df)          In: 거래df(정렬)            Out: 블록 워크포워드 OOS Δ DataFrame
#  yearly_fold(df)           In: 거래df                  Out: 연도별 기준선 vs 룰 DataFrame (+2024게이트)
#
# ── 핵심 상수 ────────────────────────────────────────────────────────────
#  LEV=22 EXP=1.559 OPV=0.25 NMULT=0.60 UP_MULT=0.30(룰)
#  MMR_T1=0.004 T2=0.005 TIER=50000 COST=0.0014 SLIP=0.0005 START=10000
#  N_BLOCKS=6 EMBARGO=1 K_OOS=(1,2,3)  CAL_KEEP=0.85(2024 Calmar 유지 게이트)
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, itertools
import numpy as np
import pandas as pd

LEV=22; EXP=1.559; OPV=0.25; NMULT=0.60; UP_MULT=0.30
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0
N_BLOCKS=6; EMBARGO=1; K_OOS=(1,2,3); CAL_KEEP=0.85
BASE=os.path.basename(__file__).replace('test_','').replace('.py','')

SEARCH=['..','.','../..','D:/ML/verify','D:/ML/Verify','../00WorkHstr','D:/ML/verify/00WorkHstr','/mnt/user-data/uploads']
def find_in_tree(cands):
    for d in SEARCH:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            h=glob.glob(os.path.join(d,c))
            if h: return h[0]
    return None

def _naive(s):
    t=pd.to_datetime(s,errors='coerce')
    try: t=t.dt.tz_localize(None)
    except (TypeError,AttributeError):
        try: t=t.dt.tz_convert(None)
        except Exception: pass
    return t

# ── 원장 + OPVnN 기준 mult ────────────────────────────────────────────────
def load_join():
    lp=find_in_tree(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    if not lp: print('!! 원장 없음 (stg6_levsweep_ledger.csv)'); sys.exit(1)
    led=pd.read_csv(lp); led['entry_t']=_naive(led['entry_t'])
    led=led.sort_values('entry_t').reset_index(drop=True)
    dp=find_in_tree(['*OPVnN*devledger*.csv','*devledger*.csv'])
    src='OPVnN'
    if dp:
        dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
        led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
        rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
        led['m_base']=np.where((led['dev'].abs()>=OPV)&(led['side']==-rd),NMULT,1.0)
    else:
        led['m_base']=1.0; src='NO_devledger(mult=1, +908% 오판주의)'
    return led, src

# ── feat_struct asof (미래참조 없음) + 캐시/폴백 ───────────────────────────
def _asof_from_source(path, keys):
    if path.lower().endswith(('.xlsx','.xls')):
        df=pd.read_excel(path, usecols=lambda c:c in ['timestamp','feat_struct_8'])
    else:
        df=pd.read_csv(path, usecols=lambda c:c in ['timestamp','feat_struct_8'])
    if 'feat_struct_8' not in df.columns: return None
    df['timestamp']=_naive(df['timestamp']); df=df.dropna(subset=['timestamp']).sort_values('timestamp')
    ts=df['timestamp'].values.astype('datetime64[ns]'); fs=df['feat_struct_8'].values
    pos=np.searchsorted(ts, keys, side='right')-1
    out=np.array([None]*len(keys),dtype=object)
    for i,pp in enumerate(pos):
        if pp>=0: out[i]=fs[pp]
    return out

def load_feat(entry_t):
    keys=entry_t.values.astype('datetime64[ns]')
    cache=f'{BASE}_featcache.csv'
    if os.path.exists(cache):  # ① 캐시 우선(가속)
        c=pd.read_csv(cache); c['entry_t']=_naive(c['entry_t'])
        mp=dict(zip(c['entry_t'], c['feat']))
        out=np.array([mp.get(pd.Timestamp(k)) for k in keys],dtype=object)
        if pd.notna(pd.Series(out)).sum()>=200: return out,'featcache'
    src=find_in_tree(['Merged_Data_with_Regime_Features.csv','Merged_Data_with_Regime_Features.xlsx',
                      '*Merged_Data_with_Regime_Features*.csv','*Regime_Features*.xlsx'])
    if src:  # ② 원본 asof (PC)
        out=_asof_from_source(src, keys)
        if out is not None and len(set(x for x in out if x is not None))>=3:  # 샘플함정 가드(장세 다양성)
            pd.DataFrame({'entry_t':entry_t.values,'feat':out}).to_csv(cache,index=False,encoding='utf-8-sig')
            return out,'source'
    jn=find_in_tree(['*RegimeRecheck_joined.csv','*joined.csv'])  # ③ 폴백: 이전 joined의 feat
    if jn:
        j=pd.read_csv(jn); j['entry_t']=_naive(j['entry_t'])
        if 'feat' in j.columns:
            mp=dict(zip(j['entry_t'], j['feat']))
            out=np.array([mp.get(pd.Timestamp(k)) for k in keys],dtype=object)
            if pd.notna(pd.Series(out)).sum()>=200:
                pd.DataFrame({'entry_t':entry_t.values,'feat':out}).to_csv(cache,index=False,encoding='utf-8-sig')
                return out,'joined_fallback'
    return np.array([None]*len(keys),dtype=object),'none'

# ── 검증된 복리엔진 + 낙폭/Calmar 추적 (numpy 루프 = 가속) ──────────────────
def compound(R, mae, fund, mult):
    n=len(R); bal=START; peak=START; mdd=0.0
    for i in range(n):
        m=mult[i]
        if m!=m: m=1.0
        mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1
        hsd=1.0/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(fund[i])) if mae[i]<=-hsd else R[i]*EXP*m
        bal*=(1.0+p)
        if bal>peak: peak=bal
        dd=bal/peak-1.0
        if dd<mdd: mdd=dd
    ret=(bal/START-1.0)*100.0
    cal=ret/abs(mdd*100.0) if mdd<0 else float('nan')
    return bal, ret, mdd*100.0, cal

def metrics(df, mcol):
    d=df.sort_values('entry_t')
    _,ret,mdd,cal=compound(d['R'].values, d['mae'].values, d['fund'].values, d[mcol].values)
    return ret,mdd,cal

# ── 블록 CPCV (고정룰 → 학습없음, OOS 조합별 효과 분포) ─────────────────────
def make_blocks(n, k_list):
    edges=np.array_split(np.arange(n), N_BLOCKS)          # 시간순 N개 블록
    combos=[]
    for k in k_list:
        for cmb in itertools.combinations(range(N_BLOCKS), k):
            idx=np.sort(np.concatenate([edges[b] for b in cmb]))
            # 퍼지: 선택 블록의 경계(연속 끊김) 양끝 EMBARGO 거래 제거(인접오염 차단)
            keep=np.ones(len(idx),bool)
            d=np.diff(idx)
            brk=np.where(d>1)[0]
            ends=np.concatenate([[0],brk+1, brk, [len(idx)-1]])
            for e in ends:
                lo=max(0,e-EMBARGO+1) if e in (brk) else e
                for off in range(EMBARGO):
                    if e+off<len(idx): keep[e+off]=False
                    if e-off>=0: keep[e-off]=False
            combos.append((cmb, idx[keep]))
    return combos

def block_cpcv(df):
    df=df.sort_values('entry_t').reset_index(drop=True)
    rows=[]
    for cmb, idx in make_blocks(len(df), K_OOS):
        if len(idx)<8: continue
        s=df.iloc[idx]
        rb=metrics(s,'m_base'); rr=metrics(s,'m_rule')
        rows.append({'blocks':'+'.join(map(str,cmb)),'n':len(idx),
                     'base_ret':round(rb[0],1),'rule_ret':round(rr[0],1),'d_ret':round(rr[0]-rb[0],1),
                     'base_mdd':round(rb[1],1),'rule_mdd':round(rr[1],1),'d_mdd':round(rr[1]-rb[1],1),
                     'base_cal':round(rb[2],2),'rule_cal':round(rr[2],2),'d_cal':round(rr[2]-rb[2],2)})
    cp=pd.DataFrame(rows)
    summ={'folds':len(cp),
          'd_ret_med':round(cp['d_ret'].median(),1),'d_ret_p25':round(cp['d_ret'].quantile(.25),1),
          'pct_ret_up':round((cp['d_ret']>0).mean()*100,0),
          'pct_mdd_better':round((cp['d_mdd']>0).mean()*100,0),   # MDD는 음수라 룰이 덜 깊으면 d_mdd>0
          'd_cal_med':round(cp['d_cal'].median(),2),'pct_cal_up':round((cp['d_cal']>0).mean()*100,0)}
    return cp, summ

def walk_forward(df):
    df=df.sort_values('entry_t').reset_index(drop=True)
    edges=np.array_split(np.arange(len(df)), N_BLOCKS)
    rows=[]
    for j in range(1,N_BLOCKS):                 # j번째 블록을 OOS로(앞은 '과거', 고정룰이라 적합없음)
        oos=df.iloc[edges[j]]
        if len(oos)<6: continue
        rb=metrics(oos,'m_base'); rr=metrics(oos,'m_rule')
        rows.append({'step':j,'oos_n':len(oos),'base_ret':round(rb[0],1),'rule_ret':round(rr[0],1),
                     'd_ret':round(rr[0]-rb[0],1),'d_mdd':round(rr[1]-rb[1],1),'d_cal':round(rr[2]-rb[2],2)})
    return pd.DataFrame(rows)

def yearly_fold(df):
    rows=[]; gate=True
    for y in sorted(df['year'].dropna().unique()):
        s=df[df['year']==y]
        rb=metrics(s,'m_base'); rr=metrics(s,'m_rule')
        keep = (rr[2]/rb[2]>=CAL_KEEP) if (rb[2]==rb[2] and rb[2]>0) else True
        if int(y)==2024 and not keep: gate=False
        rows.append({'year':int(y),'n':len(s),'base_ret':round(rb[0],1),'rule_ret':round(rr[0],1),
                     'd_ret':round(rr[0]-rb[0],1),'base_mdd':round(rb[1],1),'rule_mdd':round(rr[1],1),
                     'base_cal':round(rb[2],2),'rule_cal':round(rr[2],2),'cal_keep':round(rr[2]/rb[2],2) if rb[2]>0 else np.nan})
    return pd.DataFrame(rows), gate

# ── 실행 ─────────────────────────────────────────────────────────────────
if __name__=='__main__':
    led, src_base = load_join()
    feat, src_feat = load_feat(led['entry_t'])
    led['feat']=feat
    led['m_rule']=np.where(led['feat']=='uptrend', led['m_base']*UP_MULT, led['m_base'])
    nmatch=int(pd.notna(pd.Series(feat)).sum()); nup=int((led['feat']=='uptrend').sum())
    print(f"[데이터] 원장 {len(led)}건 / mult출처={src_base} / feat출처={src_feat} 매칭={nmatch} / uptrend={nup}")

    pd.set_option('display.width',240); pd.set_option('display.max_columns',24)
    # 1) 전체기간 기준선 vs 룰
    rb=metrics(led,'m_base'); rr=metrics(led,'m_rule')
    print(f"\n[전체] 기준선  ret{rb[0]:+.0f}% MDD{rb[1]:.1f}% Calmar{rb[2]:.2f}")
    print(f"[전체] 0.3룰   ret{rr[0]:+.0f}% MDD{rr[1]:.1f}% Calmar{rr[2]:.2f}  (Δret{rr[0]-rb[0]:+.0f} Δmdd{rr[1]-rb[1]:+.1f} Δcal{rr[2]-rb[2]:+.2f})")
    # 2) 연도 폴드 + 2024 게이트
    yf, gate = yearly_fold(led)
    print("\n[연도 폴드] 기준선 vs 0.3룰"); print(yf.to_string(index=False))
    print(f"  >> 2024 Calmar 유지 게이트(>= {CAL_KEEP}): {'PASS' if gate else 'FAIL'}")
    # 3) 블록 CPCV
    cp, cs = block_cpcv(led)
    print(f"\n[블록 CPCV] {cs['folds']}개 OOS 조합  중앙Δret{cs['d_ret_med']:+} p25Δret{cs['d_ret_p25']:+} "
          f"수익개선{cs['pct_ret_up']:.0f}% MDD개선{cs['pct_mdd_better']:.0f}% Calmar개선{cs['pct_cal_up']:.0f}% (중앙Δcal{cs['d_cal_med']:+})")
    # 4) 워크포워드
    wf = walk_forward(led)
    print("\n[워크포워드 OOS]"); print(wf.to_string(index=False))

    # 저장 (cwd=하위폴더). check.py 가 읽어 검사.
    summ=pd.DataFrame([{'base_ret':round(rb[0]),'base_mdd':round(rb[1],1),'base_cal':round(rb[2],2),
                        'rule_ret':round(rr[0]),'rule_mdd':round(rr[1],1),'rule_cal':round(rr[2],2),
                        'd_ret':round(rr[0]-rb[0]),'d_mdd':round(rr[1]-rb[1],1),'d_cal':round(rr[2]-rb[2],2),
                        'feat_match':nmatch,'uptrend_n':nup,'gate_2024':int(gate),
                        'cpcv_folds':cs['folds'],'cpcv_ret_up%':cs['pct_ret_up'],'cpcv_mdd_better%':cs['pct_mdd_better'],
                        'cpcv_cal_up%':cs['pct_cal_up'],'mult_src':src_base,'feat_src':src_feat}])
    summ.to_csv(f'{BASE}_summary.csv',index=False,encoding='utf-8-sig')
    cp.to_csv(f'{BASE}_cpcv.csv',index=False,encoding='utf-8-sig')
    yf.to_csv(f'{BASE}_yearly.csv',index=False,encoding='utf-8-sig')
    wf.to_csv(f'{BASE}_wf.csv',index=False,encoding='utf-8-sig')
    print(f"\n[저장] {BASE}_summary.csv / _cpcv.csv / _yearly.csv / _wf.csv / _featcache.csv")
