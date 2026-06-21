# [파일명] test_07Prj_Ch2_Stg6_TrendStack_RegimeRecheck.py
# 코드길이: 약 250줄 / 내부버전: build6_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 원장 장세(label_smc_8=미래참조)로 본 약점(dead_range·uptrend PF낮음)이,
#        진입시점에 쓸 수 있는 feat_struct_8(실시간)로 재라벨해도 재현되는지 검증.
#        재현되면 진입필터 가능, 아니면 미래참조 환상(접음).
#        복리는 레버22·EXP1.559·OPVnN(반대0.6)·하드스탑·MMR티어 (best.csv +586% 검증된 엔진).
#
# [미래참조 차단] feat_struct_8을 7h 진입봉 닫힘 시점 entry_t '이하' 최근값으로 asof(backward).
#                label_smc_8은 비교(교차표)용으로만 읽고 필터엔 절대 안 씀.
#
# ── 사용 파일 (상위 D:\ML\verify 자동탐지) ──────────────────────────────
#  IN  stg6_levsweep_ledger.csv          : 원장 entry_t,side,R,reason,regime(label_smc),fng,fund,mae,year
#  IN  *OPVnN*devledger*.csv             : dev,regime_dir (OPVnN mult용)
#  IN  Merged_Data_with_Regime_Features* : timestamp,feat_struct_8[,label_smc_8] (csv/xlsx)
#  OUT (반환) feat_struct 장세별 채점표 + 교차표
#
# ── 함수 (In/Out) ───────────────────────────────────────────────────────
#  find_in_tree(c)        In: 후보명          Out: 경로|None
#  load_join()            In: -               Out: 원장+OPVnN mult 결합 DataFrame
#  load_featstruct(led,p) In: 원장·feat파일    Out: feat_struct_8 ndarray (entry_t asof)
#  pnl_compound(df)       In: 거래df(정렬)     Out: (최종잔액, pnl배열)  ← 검증된 복리엔진
#  grp_stats(df,by)       In: df·기준컬럼      Out: 장세별 PF/승률/손익비/거래수/복리 DataFrame
#  yearly_pf(df,by)       In: df·기준          Out: 장세×연도 PF 피벗
#  crosstab(df)           In: df               Out: label_smc × feat_struct 교차표
#
# ── 핵심 상수 ────────────────────────────────────────────────────────────
#  LEV=22 EXP=1.559 OPV=0.25 NMULT=0.60 MMR_T1=0.004 T2=0.005 TIER=50000 COST=0.0014 SLIP=0.0005
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob
import numpy as np
import pandas as pd

LEV=22; EXP=1.559; OPV=0.25; NMULT=0.60
MMR_T1=0.004; MMR_T2=0.005; TIER=50000.0; COST=0.0014; SLIP=0.0005; START=10000.0

SEARCH=['..','.','../..','D:/ML/verify','D:/ML/Verify','/home/claude/work','/mnt/user-data/uploads']
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

def load_join():
    lp=find_in_tree(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv'])
    led=pd.read_csv(lp); led['entry_t']=_naive(led['entry_t'])
    led=led.sort_values('entry_t').reset_index(drop=True)
    dp=find_in_tree(['*OPVnN*devledger*.csv','*devledger*.csv'])
    if dp:
        dv=pd.read_csv(dp); dv['entry_t']=_naive(dv['entry_t'])
        led=led.merge(dv[['entry_t','dev','regime_dir']],on='entry_t',how='left')
    else:
        led['dev']=np.nan; led['regime_dir']=np.nan
    rd=led['regime_dir'].where((led['regime_dir']==1)|(led['regime_dir']==-1))
    led['mult']=np.where((led['dev'].abs()>=OPV)&(led['side']==-rd),NMULT,1.0)
    return led

def load_featstruct(led, path):
    keys=led['entry_t'].values.astype('datetime64[ns]')
    if path is None: return np.array([None]*len(led),dtype=object), None
    if path.lower().endswith(('.xlsx','.xls')):
        df=pd.read_excel(path, usecols=lambda c:c in ['timestamp','feat_struct_8','label_smc_8'])
    else:
        df=pd.read_csv(path, usecols=lambda c:c in ['timestamp','feat_struct_8','label_smc_8'])
    df['timestamp']=_naive(df['timestamp']); df=df.dropna(subset=['timestamp']).sort_values('timestamp')
    ts=df['timestamp'].values.astype('datetime64[ns]')
    fs=df['feat_struct_8'].values if 'feat_struct_8' in df.columns else np.array([None]*len(df),dtype=object)
    pos=np.searchsorted(ts, keys, side='right')-1     # entry_t 이하 최근(backward)
    out=np.array([None]*len(led),dtype=object)
    for i,pp in enumerate(pos):
        if pp>=0: out[i]=fs[pp]
    return out, df

def pnl_compound(df):
    df=df.sort_values('entry_t'); bal=START; arr=[]
    for _,r in df.iterrows():
        m=r['mult']; mmr=MMR_T2 if EXP*m*bal>TIER else MMR_T1; hsd=1/LEV-mmr-SLIP
        p=-EXP*m*(hsd+COST+abs(r['fund'])) if r['mae']<=-hsd else r['R']*EXP*m
        bal*=(1+p); arr.append(p)
    return bal, np.array(arr)

def grp_stats(df, by):
    rows=[]
    for k in sorted([x for x in df[by].dropna().unique()]):
        s=df[df[by]==k]; n=len(s)
        win=s[s['R']>0]['R']; loss=s[s['R']<=0]['R']
        PF=win.sum()/(-loss.sum()) if loss.sum()<0 else np.inf
        aw=win.mean() if len(win) else 0.0; al=-loss.mean() if len(loss) else 0.0
        bal,_=pnl_compound(s)
        rows.append({'feat_struct':k,'거래수':n,'PF':round(PF,2),'승률%':round(len(win)/n*100,1),
                     '손익비':round(aw/al,2) if al>0 else np.inf,
                     '평균익%':round(aw*100,2),'평균손%':round(al*100,2),
                     '수익률%':round((bal/START-1)*100,0),'수익금$':round(bal-START,0)})
    return pd.DataFrame(rows)

def yearly_pf(df, by):
    def pf(s):
        w=s[s['R']>0]['R'].sum(); l=-s[s['R']<=0]['R'].sum()
        return round(w/l,2) if l>0 else np.nan
    return df.groupby([by,'year']).apply(pf,include_groups=False).unstack()

def crosstab(df):
    if 'feat' not in df.columns: return None
    return pd.crosstab(df['regime'], df['feat'])

if __name__=='__main__':
    led=load_join()
    fpath=find_in_tree(['Merged_Data_with_Regime_Features.csv','Merged_Data_with_Regime_Features.xlsx',
                        '*Merged_Data_with_Regime_Features*.csv','*Regime_Features*.xlsx'])
    print("[경로] ledger / feat:", fpath)
    feat,_=load_featstruct(led, fpath)
    led['feat']=feat
    nmatch=int(pd.notna(pd.Series(feat)).sum())
    print(f"feat_struct 매칭: {nmatch}/{len(led)}")

    allb,_=pnl_compound(led)
    print(f"\n[전체 264] 레버22 EXP1.559 OPVnN: ${allb:,.0f} ({(allb/START-1)*100:+.0f}%)")

    pd.set_option('display.width',240); pd.set_option('display.max_columns',20)
    print("\n[A] feat_struct_8(실시간) 장세별 성과")
    ga=grp_stats(led,'feat'); print(ga.to_string(index=False))

    print("\n[B] 비교용: label_smc_8(미래참조,원장regime) 장세별 PF")
    gb=grp_stats(led,'regime')[['feat_struct','거래수','PF','수익률%']]
    gb.columns=['label_smc','거래수','PF','수익률%']; print(gb.to_string(index=False))

    print("\n[C] label_smc × feat_struct 교차표 (일치도)")
    ct=crosstab(led)
    if ct is not None: print(ct.to_string())

    print("\n[D] feat_struct 장세 × 연도 PF (안정성)")
    yp=yearly_pf(led,'feat'); print(yp.to_string())

    base=os.path.basename(__file__).replace('test_','').replace('.py','')
    ga.to_csv(base+'_featstruct.csv',index=False,encoding='utf-8-sig')
    led[['entry_t','side','R','mae','year','regime','feat','mult']].to_csv(base+'_joined.csv',index=False,encoding='utf-8-sig')
    if ct is not None: ct.to_csv(base+'_crosstab.csv',encoding='utf-8-sig')
    print(f"\n[저장] {base}_featstruct.csv / _joined.csv / _crosstab.csv")
