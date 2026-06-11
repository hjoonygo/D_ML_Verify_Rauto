# [파일명] test_07Prj_Ch3_Stg3_TrendStack_OPVnNRemoval.py
# 코드길이: 약 235줄 / 내부버전: build_ch3s3_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] E1: "Stg2 uptrend숏컷이 깔린 지금 OPVnN(역추세 진입 NMULT배)을 제거(NMULT=1.0)해도 되나?"
#        NMULT를 1.0(제거)→0.2로 스윕하고, MDD<=-20% 한도를 전 구간(전체+연도+CPCV폴드)에서 지키는지로 판정.
#        고정룰: uptrend & 추세역행 숏(side=-1) → 진입수량 0 (Stg2 채택분).
#        측정 선결과: NMULT=1.0(제거)은 +1307%지만 MDD-22.4% = 한도 위반 → 제거 불가 가설.
#        NMULT는 '역추세 수량 = MDD 다이얼'. 본 테스트는 한도 내 최적 NMULT를 CPCV로 확정한다.
#
# [미래참조 차단] feat_struct_8 asof backward·label_smc 미사용·shift(-) 없음.
# [속도] numpy 복리·feat usecols+searchsorted·featcache·고정룰이라 폴드당 1회 복리.
# ── IN: stg6_levsweep_ledger.csv / *OPVnN*devledger*.csv(dev,regime_dir) / Merged_Data_with_Regime_Features(폴백 *featcache/*joined)
#    OUT(cwd): <BASE>_sweep.csv(NMULT별 전체+가드) / _yearly.csv(선정NMULT 연도별) / _cpcv.csv / _wf.csv / _summary.csv / _featcache.csv
# ── 함수: find_in_tree/_naive/load_join(원장+dev+regime_dir+ctr마스크)/load_feat(asof)/
#         mult_for(led,nmult)=숏컷고정+역추세 NMULT / compound(낙폭추적) / block_cpcv/walk_forward/yearly_fold(MDD가드)
# ── 상수: LEV22 EXP1.559 OPV0.25 / NMULT_SWEEP=[1.0,0.8,0.6,0.4,0.2] (1.0=OPVnN제거) / SHORT_CUT=0.0(고정)
#         MMR_T1.004 T2.005 TIER50000 COST.0014 SLIP.0005 START10000 / N_BLOCKS6 EMBARGO1 K_OOS(1,2,3) MDD_LIMIT-20.0
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob, itertools
import numpy as np, pandas as pd

LEV=22; EXP=1.559; OPV=0.25
NMULT_SWEEP=[1.0,0.8,0.6,0.4,0.2]; SHORT_CUT=0.0
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
    dp=find_in_tree(['*OPVnN*devledger*.csv','*devledger*.csv'])
    if not dp: print('!! devledger 없음 — OPVnN 검증 불가(dev,regime_dir 필요)'); sys.exit(1)
    dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
    led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
    rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
    led['ctr']=((led['dev'].abs()>=OPV)&(led['side']==-rd)).fillna(False)   # OPVnN 대상(역추세 진입)
    return led

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

# ── mult: 역추세 진입은 NMULT배, 단 uptrend숏은 무조건 0 (Stg2 고정) ──
def mult_for(led, nmult):
    up_sh=((led['feat']=='uptrend')&(led['side']==-1)).values
    base=np.where(led['ctr'].values, nmult, 1.0)
    return np.where(up_sh, SHORT_CUT, base)

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
    return ret, mdd*100.0, (ret/abs(mdd*100.0) if mdd<0 else float('nan'))

def make_blocks(n):
    edges=np.array_split(np.arange(n), N_BLOCKS); combos=[]
    for k in K_OOS:
        for cmb in itertools.combinations(range(N_BLOCKS), k):
            idx=np.sort(np.concatenate([edges[b] for b in cmb]))
            keep=np.ones(len(idx),bool); d=np.diff(idx)
            brk=set(np.where(d>1)[0])|{0,len(idx)-1}|set(b+1 for b in np.where(d>1)[0])
            for e in brk:
                for off in range(EMBARGO):
                    if 0<=e+off<len(idx): keep[e+off]=False
                    if 0<=e-off<len(idx): keep[e-off]=False
            combos.append(idx[keep])
    return combos
def cpcv_worst_mdd(led, nmult):
    d=led.sort_values('entry_t').reset_index(drop=True); mt=mult_for(d, nmult); worst=0.0; n=0
    R=d['R'].values; mae=d['mae'].values; fund=d['fund'].values
    for idx in make_blocks(len(d)):
        if len(idx)<8: continue
        _,m,_=compound(R[idx],mae[idx],fund[idx],mt[idx]); worst=min(worst,m); n+=1
    return round(worst,1), n
def yearly_fold(led, nmult):
    rows=[]; worst_year=0.0
    for y in sorted(led['year'].dropna().unique()):
        s=led[led['year']==y]; mt=mult_for(s,nmult)
        r,m,c=compound(s['R'].values,s['mae'].values,s['fund'].values,mt)
        rows.append({'year':int(y),'n':len(s),'rule_ret':round(r),'rule_mdd':round(m,1)})
        worst_year=min(worst_year,m)
    return pd.DataFrame(rows), round(worst_year,1)
def walk_forward(led, nmult):
    d=led.sort_values('entry_t').reset_index(drop=True); edges=np.array_split(np.arange(len(d)),N_BLOCKS); rows=[]
    mt=mult_for(d,nmult)
    for j in range(1,N_BLOCKS):
        ix=edges[j]
        if len(ix)<6: continue
        _,m,_=compound(d['R'].values[ix],d['mae'].values[ix],d['fund'].values[ix],mt[ix])
        rows.append({'step':j,'oos_n':len(ix),'oos_mdd':round(m,1)})
    return pd.DataFrame(rows)

if __name__=='__main__':
    led=load_join(); feat,src_feat=load_feat(led['entry_t']); led['feat']=feat
    nctr=int(led['ctr'].sum()); nush=int(((led['feat']=='uptrend')&(led['side']==-1)).sum())
    print(f"[데이터] {len(led)}건 / feat출처={src_feat} / 역추세진입(OPVnN대상)={nctr} / uptrend숏(고정0)={nush}")
    pd.set_option('display.width',240)
    R=led['R'].values;mae=led['mae'].values;fund=led['fund'].values
    # NMULT 스윕 + 3중 MDD가드(전체·연도·CPCV폴드)
    rows=[]
    for nm in NMULT_SWEEP:
        mt=mult_for(led,nm); ret,mdd,cal=compound(R,mae,fund,mt)
        wf_mdd,nf=cpcv_worst_mdd(led,nm); _,wy=yearly_fold(led,nm)
        passg = (mdd>=MDD_LIMIT) and (wf_mdd>=MDD_LIMIT) and (wy>=MDD_LIMIT)
        rows.append({'NMULT':nm,'수익률%':round(ret),'MDD%':round(mdd,1),'Calmar':round(cal,1),
                     '연도최악MDD':wy,'CPCV최악MDD':wf_mdd,'가드(-20%)':'PASS' if passg else 'FAIL',
                     '비고':'OPVnN제거' if nm==1.0 else ('현Stg2' if nm==0.6 else '')})
    sweep=pd.DataFrame(rows)
    print("\n[NMULT 스윕] (uptrend숏컷 고정) — 1.0=OPVnN 제거"); print(sweep.to_string(index=False))
    # 선정: 가드 PASS 중 Calmar 최대
    BUFFER=-18.0   # -20% 한도에 2%p 안전여유: in-sample CPCV는 낙관적이라 라이브 위반 방지
    sweep['worst_all']=sweep[['MDD%','연도최악MDD','CPCV최악MDD']].min(axis=1)
    safe=sweep[sweep['worst_all']>=BUFFER]
    if len(safe)==0:
        nm_best=NMULT_SWEEP[-1]; print("  !! 안전여유 통과 NMULT 없음 — 최타이트 채택")
    else:
        nm_best=float(safe.sort_values('Calmar',ascending=False).iloc[0]['NMULT'])
    removal_ok = bool(sweep[sweep['NMULT']==1.0]['가드(-20%)'].iloc[0]=='PASS')
    print(f"  >> OPVnN 제거(NMULT=1.0): {'제거가능' if removal_ok else 'FAIL=제거불가(-20% 위반)'} / 안전여유(-18%p) 내 최적 NMULT={nm_best}")

    yf,wy=yearly_fold(led,nm_best); print(f"\n[연도 폴드] NMULT={nm_best}"); print(yf.to_string(index=False))
    cpv=walk_forward(led,nm_best)
    # CPCV 상세 저장용
    d=led.sort_values('entry_t').reset_index(drop=True); mt=mult_for(d,nm_best); crows=[]
    for k,idx in enumerate(make_blocks(len(d))):
        if len(idx)<8: continue
        _,m,c=compound(d['R'].values[idx],d['mae'].values[idx],d['fund'].values[idx],mt[idx])
        crows.append({'fold':k,'n':len(idx),'mdd':round(m,1),'calmar':round(c,1) if c==c else None})
    cp=pd.DataFrame(crows); wf_mdd=cp['mdd'].min()
    print(f"\n[블록 CPCV] NMULT={nm_best}: {len(cp)}폴드 최악MDD{wf_mdd}% (한도-20%)")
    print("[워크포워드]"); print(cpv.to_string(index=False))

    ret,mdd,cal=compound(R,mae,fund,mult_for(led,nm_best))
    summ=pd.DataFrame([{'nmult_best':nm_best,'removal_ok':int(removal_ok),'rule_ret':round(ret),'rule_mdd':round(mdd,1),
        'rule_cal':round(cal,1),'worst_year_mdd':wy,'worst_cpcv_mdd':round(float(wf_mdd),1),
        'ctr_n':nctr,'uptrend_short_n':nush,'mdd_limit':MDD_LIMIT,'feat_src':src_feat}])
    summ.to_csv(f'{BASE}_summary.csv',index=False,encoding='utf-8-sig')
    sweep.to_csv(f'{BASE}_sweep.csv',index=False,encoding='utf-8-sig')
    yf.to_csv(f'{BASE}_yearly.csv',index=False,encoding='utf-8-sig')
    cp.to_csv(f'{BASE}_cpcv.csv',index=False,encoding='utf-8-sig')
    cpv.to_csv(f'{BASE}_wf.csv',index=False,encoding='utf-8-sig')
    print(f"\n[저장] {BASE}_summary/_sweep/_yearly/_cpcv/_wf.csv")
