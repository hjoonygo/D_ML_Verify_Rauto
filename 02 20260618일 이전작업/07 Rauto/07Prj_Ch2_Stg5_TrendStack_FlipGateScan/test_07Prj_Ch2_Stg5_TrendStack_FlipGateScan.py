# [파일명] test_07Prj_Ch2_Stg5_TrendStack_FlipGateScan.py
# 코드길이: 약 330줄 / 내부버전: build5_v1 / 로직 축약·생략 없이 전체 출력
# ─────────────────────────────────────────────────────────────────────────
# [목적] 추세봇 TrendStack 264거래 중 '전환형 64건'(깊은 역행 후 회복 못함, PF0)을
#        나머지 200건(정상191+회복형9)과, 진입 결정시점에 알 수 있는 '가격 외부 정보'로
#        분리할 수 있는지 측정. 슬리피지는 제외(데이터 없음·가치 미검증). 측정 먼저.
#
# [전환형 정의 — 원장 mae·R 기준]  deep=(mae<=-0.02)  recover=((R-mae)>=0.03)
#   정상   = not deep                 (얕은 역행)
#   회복형 = deep and recover         (깊게 역행 후 3%+ 복귀 — 살릴 것)
#   전환형 = deep and not recover     (깊게 역행 후 복귀 실패 — 거를 것) ← 분리 대상(label=1)
#
# [미래참조 차단] 모든 피처는 진입봉(7h) 닫힘 시점 entry_t '이전' 값만 asof로 매칭.
#                Pauto 미시도 timestamp < entry_t 인 봉만 사용. label_smc 미사용.
#
# ── 사용 파일 (전부 한 단계 상위 D:\ML\verify 또는 자동탐지) ──────────────
#  IN  stg6_levsweep_ledger.csv     : 원장. entry_t,side,R,reason,regime,fng,entry_price,fund,mae,year
#  IN  Merged_Data.csv(merged_data.csv): 1분봉 거시. timestamp,oi_change_1h_pct,oi_drop_after_spike,
#                                        top_retail_divergence,taker_imbalance_5m_avg,oi_zscore_24h,close
#  IN  *funding*8h*.csv             : 8h 펀딩. fundingTime,fundingRate
#  IN  *CVD*15m*.csv                : 15분 CVD. timestamp,delta
#  IN  *Pauto_Continuous*.csv       : 264거래 전후 14시간 1분봉. signal_event_time,timestamp,volume,trades,taker_base_vol
#  OUT (반환) 피처별 채점 DataFrame  → CSV 저장은 호출부(__main__)에서
#
# ── 함수 목록 (In/Out) ──────────────────────────────────────────────────
#  find_in_tree(cands)            In: 후보파일명 list           Out: 실제 경로 str|None  (..·.·절대 자동탐지)
#  load_ledger(path)              In: 원장경로                  Out: DataFrame(entry_t[dt],side,R,mae,fng,year,label)
#  asof_series(ts_idx,val,keys)   In: 정렬된 시각·값·조회시각들   Out: keys 직전값 ndarray (미래참조 없음)
#  match_macro(led,path)          In: 원장df·merged경로          Out: dict{피처명:ndarray} + 가격추세 ret7h
#  match_funding(led,path)        In: 원장df·funding경로         Out: (fundingRate ndarray, funding_div ndarray)
#  match_cvd(led,path)            In: 원장df·CVD경로             Out: cvd_1h ndarray (직전 4개 15분 delta 합)
#  match_micro(led,path)          In: 원장df·Pauto경로           Out: (taker_imb_60m ndarray, tick_dens ndarray)
#  auc_score(x,y)                 In: 피처값·라벨(1=전환)         Out: AUC float (NaN 안전)
#  perm_p(x,y,n)                  In: 피처값·라벨·반복수          Out: 순열검정 p (|AUC-0.5| 기준)
#  yearly_auc(x,y,yr)             In: 피처값·라벨·연도            Out: dict{연도:AUC}
#  verdict(corr,auc,yauc,p)       In: 채점값들                   Out: 판정 str (알파후보/약함/무효/가격파생)
#  run_scan(paths)                In: 경로dict                  Out: 채점 DataFrame
#
# ── 핵심 상수 ────────────────────────────────────────────────────────────
#  DEEP=-0.02  RECOVER=0.03  TF_MIN=420(7h)  MICRO_MIN=60  AUC_HI=0.65  CORR_HI=0.5  PERM_N=2000
# ─────────────────────────────────────────────────────────────────────────
import os, sys, glob
import numpy as np
import pandas as pd

DEEP=-0.02; RECOVER=0.03; TF_MIN=420; MICRO_MIN=60
AUC_HI=0.65; CORR_HI=0.5; PERM_N=2000
RNG=np.random.default_rng(7)

# ── 데이터 자동탐지: 하위폴더 안에서 실행되므로 상위(..) 우선 ──────────────
SEARCH_DIRS = ['..', '.', '../..', 'D:/ML/verify', 'D:/ML/Verify',
               '/home/claude/work/container_verify', '/mnt/user-data/uploads']
def find_in_tree(cands):
    for d in SEARCH_DIRS:
        for c in cands:
            p=os.path.join(d,c)
            if os.path.exists(p): return p
            hits=glob.glob(os.path.join(d,c))
            if hits: return hits[0]
    return None

def _to_naive(s):
    t=pd.to_datetime(s, errors='coerce')
    try: t=t.dt.tz_localize(None)
    except (TypeError, AttributeError):
        try: t=t.dt.tz_convert(None)
        except Exception: pass
    return t

# ── 원장 + 라벨 ──────────────────────────────────────────────────────────
def load_ledger(path):
    df=pd.read_csv(path)
    df['entry_t']=_to_naive(df['entry_t'])
    mae=df['mae'].values; R=df['R'].values
    deep = mae<=DEEP
    recover = (R-mae)>=RECOVER
    df['label']=np.where(deep & ~recover, 1, 0)   # 1=전환형
    df=df.sort_values('entry_t').reset_index(drop=True)
    return df

# ── asof: keys 각각에 대해 ts_idx<key 인 마지막 val (미래참조 없음) ────────
def asof_series(ts_idx, val, keys):
    ts_idx=np.asarray(ts_idx); val=np.asarray(val, dtype='float64'); keys=np.asarray(keys)
    order=np.argsort(ts_idx); ts_idx=ts_idx[order]; val=val[order]
    pos=np.searchsorted(ts_idx, keys, side='right')-1   # < key 인 마지막
    out=np.full(len(keys), np.nan)
    ok=pos>=0
    out[ok]=val[pos[ok]]
    return out

# ── 거시 피처 (merged_data) ──────────────────────────────────────────────
def match_macro(led, path):
    use=['timestamp','oi_change_1h_pct','oi_drop_after_spike','top_retail_divergence',
         'taker_imbalance_5m_avg','oi_zscore_24h','close']
    df=pd.read_csv(path, usecols=lambda c: c in use)
    df['timestamp']=_to_naive(df['timestamp'])
    df=df.dropna(subset=['timestamp']).sort_values('timestamp')
    ts=df['timestamp'].values.astype('datetime64[ns]')
    keys=led['entry_t'].values.astype('datetime64[ns]')
    feats={}
    for col in ['oi_change_1h_pct','oi_drop_after_spike','top_retail_divergence',
                'taker_imbalance_5m_avg','oi_zscore_24h']:
        feats[col]= asof_series(ts, df[col].values, keys) if col in df.columns else np.full(len(keys),np.nan)
    # 진입전 7h 가격추세: entry_t 시점 close / 420분 전 close - 1
    close_now = asof_series(ts, df['close'].values, keys)
    close_pre = asof_series(ts, df['close'].values, keys - np.timedelta64(TF_MIN,'m'))
    ret7h = close_now/close_pre - 1.0
    feats['_ret7h']=ret7h
    return feats

# ── 펀딩 + 다이버전스 ────────────────────────────────────────────────────
def match_funding(led, path, ret7h):
    df=pd.read_csv(path)
    tcol='fundingTime' if 'fundingTime' in df.columns else df.columns[0]
    df[tcol]=_to_naive(df[tcol]); df=df.dropna(subset=[tcol]).sort_values(tcol)
    ts=df[tcol].values.astype('datetime64[ns]')
    keys=led['entry_t'].values.astype('datetime64[ns]')
    fr=asof_series(ts, df['fundingRate'].values, keys)
    # 다이버전스: 가격↑(ret7h>0)인데 펀딩↓(fr<0) → 양수 신호 (가격과 어긋난 외부정보)
    div = -np.sign(ret7h) * fr
    return fr, div

# ── CVD (직전 1h = 15분 4개 delta 합) ────────────────────────────────────
def match_cvd(led, path):
    df=pd.read_csv(path)
    tcol='timestamp' if 'timestamp' in df.columns else df.columns[0]
    df[tcol]=_to_naive(df[tcol]); df=df.dropna(subset=[tcol]).sort_values(tcol)
    ts=df[tcol].values.astype('datetime64[ns]')
    d=df['delta'].values.astype('float64')
    cum=np.concatenate([[0.0], np.cumsum(d)])          # 누적합으로 구간합 빠르게
    keys=led['entry_t'].values.astype('datetime64[ns]')
    pos_now=np.searchsorted(ts, keys, side='right')          # < key 개수
    pos_pre=np.searchsorted(ts, keys - np.timedelta64(60,'m'), side='right')
    out=np.full(len(keys), np.nan)
    ok=pos_now>0
    out[ok]=cum[pos_now[ok]]-cum[pos_pre[ok]]
    return out

# ── 미시 (Pauto 연속) : 진입 직전 60분 taker 불균형 + 틱 밀도 ─────────────
def match_micro(led, path):
    keys_dt=led['entry_t']
    taker=np.full(len(led), np.nan); dens=np.full(len(led), np.nan)
    if path is None or not os.path.exists(path):
        return taker, dens
    # signal_event_time 별로 그룹 → 진입 직전 60분만
    df=pd.read_csv(path, usecols=lambda c: c in
        ['signal_event_time','timestamp','volume','trades','taker_base_vol'])
    df['timestamp']=_to_naive(df['timestamp'])
    df['sig']=pd.to_datetime(df['signal_event_time'].astype(str), format='%Y%m%d_%H%M%S', errors='coerce')
    g=df.groupby('sig')
    sig_map={k:v for k,v in g}
    for i,et in enumerate(keys_dt):
        seg=sig_map.get(et)
        if seg is None: continue
        pre=seg[seg['timestamp']<et]
        if len(pre)==0: continue
        last=pre[pre['timestamp']>=et-pd.Timedelta(minutes=MICRO_MIN)]
        if len(last)==0: last=pre.tail(MICRO_MIN)
        v=last['volume'].sum()
        if v>0 and 'taker_base_vol' in last:
            taker[i]=last['taker_base_vol'].sum()/v - 0.5     # >0 매수 우위
        if 'trades' in last and len(pre)>0:
            base=pre['trades'].mean()
            dens[i]= last['trades'].mean()/base if base>0 else np.nan  # >1 틱 가속
    return taker, dens

# ── AUC (Mann-Whitney) ───────────────────────────────────────────────────
def auc_score(x, y):
    x=np.asarray(x,dtype='float64'); y=np.asarray(y)
    m=~np.isnan(x); x=x[m]; y=y[m]
    n1=int((y==1).sum()); n0=int((y==0).sum())
    if n1==0 or n0==0: return np.nan
    order=np.argsort(x, kind='mergesort'); ranks=np.empty(len(x)); ranks[order]=np.arange(1,len(x)+1)
    # 동점 평균순위
    _,inv,cnt=np.unique(x,return_inverse=True,return_counts=True)
    csum=np.cumsum(cnt); start=csum-cnt
    avg=(start+csum+1)/2.0
    ranks=avg[inv]
    return (ranks[y==1].sum()-n1*(n1+1)/2)/(n1*n0)

def perm_p(x, y, n=PERM_N):
    a=auc_score(x,y)
    if np.isnan(a): return np.nan
    obs=abs(a-0.5); yy=y.copy(); hit=0
    m=~np.isnan(np.asarray(x,dtype='float64'))
    xs=np.asarray(x,dtype='float64')[m]; ys=yy[m]
    for _ in range(n):
        if abs(auc_score(xs, RNG.permutation(ys))-0.5)>=obs: hit+=1
    return (hit+1)/(n+1)

def yearly_auc(x, y, yr):
    out={}
    for u in sorted(pd.unique(yr)):
        mm=yr==u
        out[int(u)]=auc_score(np.asarray(x)[mm], np.asarray(y)[mm])
    return out

def verdict(corr, auc, yauc, p):
    if np.isnan(auc): return 'DATA없음'
    sep=abs(auc-0.5)
    if abs(corr)>=CORR_HI: return '가격파생(탈락)'
    vals=[v for v in yauc.values() if not np.isnan(v)]
    same = all((v-0.5)*(auc-0.5)>0 for v in vals) if vals else False  # 연도 방향 일치
    if sep>=(AUC_HI-0.5) and (p is not None and p<0.05) and same: return '★알파후보'
    if sep>=0.10 and same: return '약한분리'
    return '무효(0.5)'

# ── 메인 스캔 ────────────────────────────────────────────────────────────
def run_scan(paths):
    led=load_ledger(paths['ledger'])
    y=led['label'].values; yr=led['year'].values
    rows=[]
    macro=match_macro(led, paths['macro']) if paths['macro'] else {}
    ret7h=macro.get('_ret7h', np.full(len(led),np.nan))
    feat={}
    for k in ['oi_change_1h_pct','oi_drop_after_spike','top_retail_divergence',
              'taker_imbalance_5m_avg','oi_zscore_24h']:
        if k in macro: feat[k]=macro[k]
    feat['fng']=led['fng'].values.astype('float64')
    if paths['funding']:
        fr,div=match_funding(led, paths['funding'], ret7h)
        feat['fundingRate']=fr; feat['funding_div']=div
    if paths['cvd']:
        feat['cvd_1h']=match_cvd(led, paths['cvd'])
    tk,dn=match_micro(led, paths['micro'])
    feat['taker_imb_60m']=tk; feat['tick_dens_60m']=dn

    for name,x in feat.items():
        x=np.asarray(x,dtype='float64')
        m=~(np.isnan(x)|np.isnan(ret7h))
        corr=np.corrcoef(x[m], ret7h[m])[0,1] if m.sum()>2 else np.nan
        auc=auc_score(x,y)
        yauc=yearly_auc(x,y,yr)
        p=perm_p(x,y) if not np.isnan(auc) else np.nan
        dirn = '—' if np.isnan(auc) else ('高=전환' if auc>0.5 else ('低=전환' if auc<0.5 else '—'))
        rows.append({'feature':name,'n_valid':int((~np.isnan(x)).sum()),
                     'price_corr':round(corr,3) if not np.isnan(corr) else np.nan,
                     'AUC_flip':round(auc,3) if not np.isnan(auc) else np.nan,
                     'sep':round(abs(auc-0.5),3) if not np.isnan(auc) else np.nan,
                     'dir':dirn,
                     'AUC_2023':round(yauc.get(2023,np.nan),3) if not np.isnan(yauc.get(2023,np.nan)) else np.nan,
                     'AUC_2024':round(yauc.get(2024,np.nan),3) if not np.isnan(yauc.get(2024,np.nan)) else np.nan,
                     'AUC_2025':round(yauc.get(2025,np.nan),3) if not np.isnan(yauc.get(2025,np.nan)) else np.nan,
                     'AUC_2026':round(yauc.get(2026,np.nan),3) if not np.isnan(yauc.get(2026,np.nan)) else np.nan,
                     'perm_p':round(p,4) if (p is not None and not np.isnan(p)) else np.nan,
                     'verdict':verdict(corr,auc,yauc,p)})
    out=pd.DataFrame(rows).sort_values('sep',ascending=False,na_position='last').reset_index(drop=True)
    return out, led

# ── 실행부 ───────────────────────────────────────────────────────────────
if __name__=='__main__':
    paths={
        'ledger': find_in_tree(['stg6_levsweep_ledger.csv','*levsweep_ledger.csv']),
        'macro' : find_in_tree(['Merged_Data.csv','merged_data.csv','merged_data*.csv']),
        'funding': find_in_tree(['*funding*8h*.csv','*funding_history*.csv','*BTCUSDT_funding*.csv']),
        'cvd'   : find_in_tree(['*CVD*15m*.csv','*CVD*BTCUSDT*.csv','sample_CVD*.csv']),
        'micro' : find_in_tree(['*Pauto_Continuous*.csv','Pauto_Continuous*.csv']),
    }
    print("[경로 탐지]")
    for k,v in paths.items(): print(f"  {k:8s}: {v}")
    if not paths['ledger']:
        print("!! 원장(stg6_levsweep_ledger.csv)을 찾지 못함. D:/ML/verify에 두세요."); sys.exit(1)

    out, led = run_scan(paths)
    pd.set_option('display.width',240); pd.set_option('display.max_columns',20)
    print("\n[전환형 분리력 스캔 결과]  (전환형 %d vs 비전환형 %d)"%((led['label']==1).sum(),(led['label']==0).sum()))
    print(out.to_string(index=False))

    base=os.path.basename(__file__).replace('test_','').replace('.py','')
    out_csv=base+'_scan.csv'
    out.to_csv(out_csv, index=False, encoding='utf-8-sig')
    led[['entry_t','side','R','mae','fng','year','label']].to_csv(base+'_labels.csv', index=False, encoding='utf-8-sig')
    print(f"\n[저장] {out_csv} / {base}_labels.csv")
