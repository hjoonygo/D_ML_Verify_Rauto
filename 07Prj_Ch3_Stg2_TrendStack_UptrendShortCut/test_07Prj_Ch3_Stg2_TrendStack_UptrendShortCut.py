# [파일명] test_07Prj_Ch3_Stg2_TrendStack_UptrendShortCut.py
# 코드길이: 약 245줄 / 내부버전: build_ch3s2_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] Stg1 단일룰(uptrend 전체 0.3배, 2024 수익 -34%p 손해)을 외과적으로 개선:
#        '실시간 uptrend 구조에서 추세역행 숏(side=-1)'만 골라 진입수량을 축소한다.
#        근거(Stg1 사후측정): uptrend 100건 = 돈버는 롱 84건(PF1.72) + 재앙 숏 16건(PF0.07),
#        숏 16건은 4년 전부 적자(매년 짐)·14/16 패 → '상승구조 역행 숏' = 구조적 약점.
#        효과(in-sample, OPVnN 기준): 숏만 0.0 → +827%/MDD-16.1%/Cal51.3 (전체0.3 +634%보다 우위, 2024도 개선).
#        ★단 16건 기반 → 크기 불신·방향만 신뢰. 보수 스윕(0.0/0.2/0.3/0.5)+CPCV+연도+MDD가드로 검증한다.
#
# [실시간 탑재형] 룰은 Rauto가 진입 직전 1줄로 판정: feat_struct_8=='uptrend' and side==-1 이면 mult*=SH.
#                realtime_mult() 가 그 박제 형태. (가격예측 아님·장세+방향만 = 미래참조 없음)
# [미래참조 차단] feat_struct_8 = 진입봉 마감 entry_t '이하' 최근값 asof(backward). label_smc 미사용. shift(-) 없음.
# [속도 최적화] numpy 배열 루프(복리)·feat usecols+단일 searchsorted·featcache 재사용·고정룰이라 폴드당 1회 복리.
#
# ── 사용 파일 (상위 D:\ML\verify 자동탐지) ──────────────────────────────
#  IN  stg6_levsweep_ledger.csv  : 원장 entry_t,side,R,fund,mae,year
#  IN  *OPVnN*devledger*.csv     : entry_t,dev,regime_dir (OPVnN 기준 mult)
#  IN  Merged_Data_with_Regime_Features.csv : timestamp,feat_struct_8 (실시간 장세; 폴백: *featcache.csv / 이전 *joined.csv)
#  OUT(cwd) <BASE>_sweep.csv  : 기준선·Stg1전체룰·숏스윕(0.0~0.5) 전체성과 비교
#  OUT(cwd) <BASE>_yearly.csv : 최적 숏승수의 연도별 기준선 vs 룰 (+MDD가드)
#  OUT(cwd) <BASE>_cpcv.csv   : 블록 CPCV 조합별 OOS Δ
#  OUT(cwd) <BASE>_wf.csv     : 워크포워드
#  OUT(cwd) <BASE>_featcache.csv : feat asof 캐시
#
# ── 함수 In/Out ──
#  find_in_tree(cands)        후보→경로|None         _naive(s) 시각→naive
#  load_join()                -→(원장+m_base, 출처)   load_feat(entry_t)→(feat, 출처) asof backward
#  rule_mult(mb,feat,side,sh) 기준mult·장세·방향·숏승수 → 적용mult (uptrend&숏이면 mb*sh)
#  realtime_mult(feat,side,mb,sh) Rauto 실시간 1줄판정 박제형 (rule_mult와 동일 로직)
#  compound(R,mae,fund,mult)  거래배열→(잔액,수익%,MDD%,Calmar)  검증엔진+낙폭추적
#  metrics(df,mult)           df·mult배열→(수익%,MDD%,Calmar)
#  make_blocks/block_cpcv(df,mult)  블록 CPCV (퍼지) → 조합별 Δ + 요약
#  walk_forward(df,mult)      블록 워크포워드 OOS Δ
#  yearly_fold(df,sh)         연도별 기준선 vs 숏룰 (+MDD-20% 가드, uptrend숏 매년적자 확인)
#
# ── 상수 ── LEV22 EXP1.559 OPV0.25 NMULT0.6 / SH_SWEEP=[0.0,0.2,0.3,0.5] S1_UP=0.3(Stg1비교)
#           MMR_T1 .004 T2 .005 TIER 50000 COST .0014 SLIP .0005 START 10000
#           N_BLOCKS6 EMBARGO1 K_OOS(1,2,3) MDD_LIMIT -20.0
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, itertools
import numpy as np, pandas as pd

LEV=22; EXP=1.559; OPV=0.25; NMULT=0.60
SH_SWEEP=[0.0,0.2,0.3,0.5]; S1_UP=0.30
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0
N_BLOCKS=6; EMBARGO=1; K_OOS=(1,2,3); MDD_LIMIT=-20.0
BASE=os.path.basename(__file__).replace('test_','').replace('.py','')
SEARCH=['..','.','../..','D:/ML/verify','D:/ML/Verify','../00WorkHstr','D:/ML/verify/00WorkHstr','/mnt/user-data/uploads']

def find_in_tree(cands):
    for d in SEARCH:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            h=glob.glob(os.path.join(d,c))
            if h: return sorted(h)[0]
    return None
def _naive(s):
    t=pd.to_datetime(s,errors='coerce')
    try: t=t.dt.tz_localize(None)
    except (TypeError,AttributeError):
        try: t=t.dt.tz_convert(None)
        except Exception: pass
    return t

def load_join():
    lp=find_in_tree(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    if not lp: print('!! 원장 없음'); sys.exit(1)
    led=pd.read_csv(lp); led['entry_t']=_naive(led['entry_t']); led=led.sort_values('entry_t').reset_index(drop=True)
    dp=find_in_tree(['*OPVnN*devledger*.csv','*devledger*.csv']); src='OPVnN'
    if dp:
        dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
        led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
        rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
        led['m_base']=np.where((led['dev'].abs()>=OPV)&(led['side']==-rd),NMULT,1.0)
    else: led['m_base']=1.0; src='NO_devledger(mult=1, +908% 오판주의)'
    return led, src

def _asof(path, keys):
    rd=(pd.read_excel if path.lower().endswith(('.xlsx','.xls')) else pd.read_csv)(path, usecols=lambda c:c in ['timestamp','feat_struct_8'])
    if 'feat_struct_8' not in rd.columns: return None
    rd['timestamp']=_naive(rd['timestamp']); rd=rd.dropna(subset=['timestamp']).sort_values('timestamp')
    ts=rd['timestamp'].values.astype('datetime64[ns]'); fs=rd['feat_struct_8'].values
    pos=np.searchsorted(ts, keys, side='right')-1
    out=np.array([None]*len(keys),dtype=object)
    for i,pp in enumerate(pos):
        if pp>=0: out[i]=fs[pp]
    return out
def load_feat(entry_t):
    keys=entry_t.values.astype('datetime64[ns]'); cache=f'{BASE}_featcache.csv'
    fc=find_in_tree([cache,'*featcache*.csv'])
    if fc:
        c=pd.read_csv(fc); c['entry_t']=_naive(c['entry_t']); mp=dict(zip(c['entry_t'],c['feat']))
        out=np.array([mp.get(pd.Timestamp(k)) for k in keys],dtype=object)
        if pd.notna(pd.Series(out)).sum()>=200: return out,'featcache'
    src=find_in_tree(['Merged_Data_with_Regime_Features.csv','Merged_Data_with_Regime_Features.xlsx','*Regime_Features*.csv','*Regime_Features*.xlsx'])
    if src:
        out=_asof(src,keys)
        if out is not None and len(set(x for x in out if x is not None))>=3:
            pd.DataFrame({'entry_t':entry_t.values,'feat':out}).to_csv(cache,index=False,encoding='utf-8-sig'); return out,'source'
    jn=find_in_tree(['*RegimeRecheck_joined.csv','*joined.csv'])
    if jn:
        j=pd.read_csv(jn); j['entry_t']=_naive(j['entry_t'])
        if 'feat' in j.columns:
            mp=dict(zip(j['entry_t'],j['feat'])); out=np.array([mp.get(pd.Timestamp(k)) for k in keys],dtype=object)
            if pd.notna(pd.Series(out)).sum()>=200:
                pd.DataFrame({'entry_t':entry_t.values,'feat':out}).to_csv(cache,index=False,encoding='utf-8-sig'); return out,'joined_fallback'
    return np.array([None]*len(keys),dtype=object),'none'

# ── 룰: uptrend & 추세역행 숏이면 진입수량 축소 (실시간 1줄 판정) ──
def realtime_mult(feat_now, side, base_mult, sh):
    return base_mult*sh if (feat_now=='uptrend' and side==-1) else base_mult
def rule_mult_arr(m_base, feat, side, sh):
    up_sh=(feat=='uptrend')&(side==-1)
    return np.where(up_sh, m_base*sh, m_base)

# ── 검증 복리엔진 + 낙폭/Calmar (numpy 루프) ──
def compound(R, mae, fund, mult):
    bal=START; peak=START; mdd=0.0
    for i in range(len(R)):
        m=mult[i]
        if m!=m: m=1.0
        mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1; hsd=1.0/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(fund[i])) if mae[i]<=-hsd else R[i]*EXP*m
        bal*=(1.0+p)
        if bal>peak: peak=bal
        dd=bal/peak-1.0
        if dd<mdd: mdd=dd
    ret=(bal/START-1.0)*100.0
    return bal, ret, mdd*100.0, (ret/abs(mdd*100.0) if mdd<0 else float('nan'))
def metrics(df, mult):
    d=df.sort_values('entry_t'); idx=d.index
    _,ret,mdd,cal=compound(d['R'].values, d['mae'].values, d['fund'].values, np.asarray(mult,dtype='float64')[df.index.get_indexer(idx)] if len(mult)==len(df) else mult)
    return ret,mdd,cal

def _mx(df, sh):
    return rule_mult_arr(df['m_base'].values, df['feat'].values, df['side'].values, sh)

def make_blocks(n):
    edges=np.array_split(np.arange(n), N_BLOCKS); combos=[]
    for k in K_OOS:
        for cmb in itertools.combinations(range(N_BLOCKS), k):
            idx=np.sort(np.concatenate([edges[b] for b in cmb]))
            keep=np.ones(len(idx),bool); d=np.diff(idx); brk=set(np.where(d>1)[0])|{len(idx)-1}|set(b+1 for b in np.where(d>1)[0])|{0}
            for e in brk:
                for off in range(EMBARGO):
                    if 0<=e+off<len(idx): keep[e+off]=False
                    if 0<=e-off<len(idx): keep[e-off]=False
            combos.append((cmb, idx[keep]))
    return combos
def block_cpcv(df, sh):
    d=df.sort_values('entry_t').reset_index(drop=True); rows=[]
    mb=d['m_base'].values; mr=rule_mult_arr(mb, d['feat'].values, d['side'].values, sh)
    for cmb, idx in make_blocks(len(d)):
        if len(idx)<8: continue
        s=d.iloc[idx]
        _,rb,mb1,cb=compound(s['R'].values,s['mae'].values,s['fund'].values, mb[idx])
        _,rr,mr1,cr=compound(s['R'].values,s['mae'].values,s['fund'].values, mr[idx])
        rows.append({'blocks':'+'.join(map(str,cmb)),'n':len(idx),'d_ret':round(rr-rb,1),
                     'rule_mdd':round(mr1,1),'d_mdd':round(mr1-mb1,1),'d_cal':round((cr-cb) if cb==cb and cr==cr else 0,2)})
    cp=pd.DataFrame(rows)
    worst=round(cp['rule_mdd'].min(),1)
    summ={'folds':len(cp),'d_ret_med':round(cp['d_ret'].median(),1),'d_ret_p25':round(cp['d_ret'].quantile(.25),1),
          'pct_ret_up':round((cp['d_ret']>0).mean()*100),'pct_mdd_better':round((cp['d_mdd']>0).mean()*100),
          'worst_fold_mdd':worst,'mdd_guard':'PASS' if worst>=MDD_LIMIT else 'FAIL'}
    return cp, summ
def walk_forward(df, sh):
    d=df.sort_values('entry_t').reset_index(drop=True); edges=np.array_split(np.arange(len(d)),N_BLOCKS); rows=[]
    mb=d['m_base'].values; mr=rule_mult_arr(mb,d['feat'].values,d['side'].values,sh)
    for j in range(1,N_BLOCKS):
        ix=edges[j]
        if len(ix)<6: continue
        s=d.iloc[ix]
        _,rb,mb1,_=compound(s['R'].values,s['mae'].values,s['fund'].values,mb[ix])
        _,rr,mr1,_=compound(s['R'].values,s['mae'].values,s['fund'].values,mr[ix])
        rows.append({'step':j,'oos_n':len(ix),'d_ret':round(rr-rb,1),'d_mdd':round(mr1-mb1,1)})
    return pd.DataFrame(rows)
def yearly_fold(df, sh):
    rows=[]; guard=True; up_sh_neg_all=True
    for y in sorted(df['year'].dropna().unique()):
        s=df[df['year']==y]
        _,rb,mb1,cb=compound(s['R'].values,s['mae'].values,s['fund'].values, s['m_base'].values)
        _,rr,mr1,cr=compound(s['R'].values,s['mae'].values,s['fund'].values, _mx(s,sh))
        ush=s[(s['feat']=='uptrend')&(s['side']==-1)]; ush_r=ush['R'].sum()*100
        if mr1<MDD_LIMIT: guard=False
        if len(ush)>0 and ush_r>0: up_sh_neg_all=False
        rows.append({'year':int(y),'n':len(s),'base_ret':round(rb),'rule_ret':round(rr),'d_ret':round(rr-rb),
                     'base_mdd':round(mb1,1),'rule_mdd':round(mr1,1),'ushort_n':len(ush),'ushort_R%':round(ush_r,1)})
    return pd.DataFrame(rows), guard, up_sh_neg_all

if __name__=='__main__':
    led, src_base = load_join()
    feat, src_feat = load_feat(led['entry_t']); led['feat']=feat
    nush=int(((led['feat']=='uptrend')&(led['side']==-1)).sum())
    print(f"[데이터] {len(led)}건 / mult출처={src_base} / feat출처={src_feat} / uptrend숏={nush}건")
    pd.set_option('display.width',240); pd.set_option('display.max_columns',24)

    R=led['R'].values; mae=led['mae'].values; fund=led['fund'].values
    def full(mult):
        _,r,m,c=compound(R,mae,fund,np.asarray(mult,dtype='float64')); return round(r),round(m,1),round(c,1)
    # 1) 스윕: 기준선 / Stg1 전체룰 / 숏 스윕
    rows=[]
    b=full(led['m_base'].values); rows.append(('기준선(무처리)','-',*b))
    s1=full(rule_mult_arr(led['m_base'].values, led['feat'].values, np.full(len(led),99), S1_UP) if False else np.where(led['feat'].values=='uptrend', led['m_base'].values*S1_UP, led['m_base'].values))
    rows.append(('Stg1: uptrend전체×0.3',S1_UP,*s1))
    for sh in SH_SWEEP:
        r=full(_mx(led,sh)); rows.append((f'Stg2: uptrend숏×{sh}',sh,*r))
    sweep=pd.DataFrame(rows,columns=['전략','숏승수','수익률%','MDD%','Calmar'])
    print("\n[스윕] uptrend 숏 진입수량 축소"); print(sweep.to_string(index=False))
    # 최적 숏승수: MDD<=-20% 지키며 Calmar 최대
    cand=[(sh,*full(_mx(led,sh))) for sh in SH_SWEEP]
    valid=[x for x in cand if x[2]>=MDD_LIMIT] or cand
    sh_best=sorted(valid,key=lambda x:-x[3])[0][0]
    print(f"  >> 선정 숏승수(SH_best, MDD<= -20% 내 Calmar최대) = {sh_best}")

    # 2) 연도 폴드 + MDD가드 + uptrend숏 매년적자 확인
    yf, guard, ush_neg = yearly_fold(led, sh_best)
    print(f"\n[연도 폴드] 기준선 vs uptrend숏×{sh_best}"); print(yf.to_string(index=False))
    print(f"  >> MDD가드(모든 연도 >= -20%): {'PASS' if guard else 'FAIL'} / uptrend숏 매년적자(구조성): {'YES' if ush_neg else 'NO'}")
    # 3) 블록 CPCV
    cp, cs = block_cpcv(led, sh_best)
    print(f"\n[블록 CPCV] {cs['folds']}조합 중앙Δret{cs['d_ret_med']:+} p25{cs['d_ret_p25']:+} 수익개선{cs['pct_ret_up']}% MDD개선{cs['pct_mdd_better']}% / 최악폴드MDD{cs['worst_fold_mdd']}% 가드{cs['mdd_guard']}")
    # 4) 워크포워드
    wf=walk_forward(led, sh_best); print("\n[워크포워드 OOS]"); print(wf.to_string(index=False))

    bb=full(led['m_base'].values); rr=full(_mx(led,sh_best))
    summ=pd.DataFrame([{'sh_best':sh_best,'base_ret':bb[0],'base_mdd':bb[1],'base_cal':bb[2],
        'rule_ret':rr[0],'rule_mdd':rr[1],'rule_cal':rr[2],'d_ret':rr[0]-bb[0],'uptrend_short_n':nush,
        'year_mdd_guard':int(guard),'ushort_neg_allyears':int(ush_neg),'cpcv_folds':cs['folds'],
        'cpcv_ret_up%':cs['pct_ret_up'],'cpcv_mdd_better%':cs['pct_mdd_better'],'worst_fold_mdd':cs['worst_fold_mdd'],
        'mdd_guard':cs['mdd_guard'],'mult_src':src_base,'feat_src':src_feat}])
    summ.to_csv(f'{BASE}_summary.csv',index=False,encoding='utf-8-sig')
    sweep.to_csv(f'{BASE}_sweep.csv',index=False,encoding='utf-8-sig')
    yf.to_csv(f'{BASE}_yearly.csv',index=False,encoding='utf-8-sig')
    cp.to_csv(f'{BASE}_cpcv.csv',index=False,encoding='utf-8-sig')
    wf.to_csv(f'{BASE}_wf.csv',index=False,encoding='utf-8-sig')
    print(f"\n[저장] {BASE}_summary/_sweep/_yearly/_cpcv/_wf.csv")
