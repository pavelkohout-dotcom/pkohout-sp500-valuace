#!/usr/bin/env python3
"""Quarterly US financial liquidity monitor; latest revised observations.
Run at repository root. Reads existing data/mzm_ratio.json, never changes it.
FRED_API_KEY optional; public FRED CSV fallback. No interpolation.
"""
import argparse, io, json, os, math
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np
import requests

ROOT=Path(__file__).resolve().parent
CODES={'assets':'BOGZ1FL664090005Q','flows':'BOGZ1FU664090005Q','GDP':'GDP','M2':'M2SL'}
BASE=pd.Period('1967Q1',freq='Q')

def fred(code):
    key=os.getenv('FRED_API_KEY','').strip()
    if key:
        try:
            params={'series_id':code,'api_key':key,'file_type':'json'}
            r=requests.get('https://api.stlouisfed.org/fred/series/observations',params=params,timeout=35);r.raise_for_status()
            df=pd.DataFrame(r.json()['observations']); s=pd.Series(pd.to_numeric(df.value,errors='coerce').values,index=pd.to_datetime(df.date))
            if s.notna().any(): return s.dropna().sort_index()
        except Exception: print(code+': API failed; trying CSV')
    try:
        r=requests.get('https://fred.stlouisfed.org/graph/fredgraph.csv',params={'id':code},timeout=35);r.raise_for_status()
        df=pd.read_csv(io.StringIO(r.text));s=pd.Series(pd.to_numeric(df[code],errors='coerce').values,index=pd.to_datetime(df.iloc[:,0]))
        if s.notna().any(): return s.dropna().sort_index()
    except Exception: pass
    raise RuntimeError('FRED series unavailable: '+code)

def quarter(s,monthly=False):
    if monthly: s=s[s.index.month.isin([3,6,9,12])]
    return s.groupby(s.index.to_period('Q')).last()

def from_mzm_json(path):
    payload=json.loads(path.read_text(encoding='utf-8'))
    if payload.get('status')!='ok': raise ValueError('MZM source status not OK')
    d=pd.DataFrame(payload['history']);s=pd.Series(pd.to_numeric(d.foreign_adjusted_mzm,errors='raise').values,index=pd.to_datetime(d.date))
    return quarter(s,monthly=True),payload.get('generated_utc')

def chain(a,f):
    end=min(a.dropna().index.max(),f.dropna().index.max())
    idx=pd.period_range(BASE,end,freq='Q'); a=a.reindex(idx); f=f.reindex(idx)
    if a.isna().any() or (a<=0).any() or f.iloc[1:].isna().any(): raise ValueError('Gap/nonpositive assets in FILI chain')
    factors=1+f/a.shift(1);factors.iloc[0]=1
    if (factors<=0).any(): raise ValueError('Nonpositive FILI factor')
    return 100*factors.cumprod()

def build(d,mzm_generated=None,mode='live_fred',today=None):
    today=today or datetime.now(timezone.utc)
    d=d.sort_index().loc[lambda x:(x.index>=BASE)&(x.index<pd.Period(today.date(),freq='Q'))]
    d=d.reindex(pd.period_range(BASE,d.index.max(),freq='Q'))
    if (d<=0).any().any(): raise ValueError('Nonpositive level')
    g=d.pct_change(4,fill_method=None)*100
    g=g.replace([np.inf,-np.inf],np.nan)
    core=['mzm','fili','gdp']; complete=g[core].dropna()
    if len(complete)<20: raise ValueError('Insufficient common observations')
    if len(complete)!=len(pd.period_range(complete.index.min(),complete.index.max(),freq='Q')): raise ValueError('Gap in common history')
    latest={k:str(g[k].last_valid_index()) for k in g.columns if g[k].notna().any()}
    def num(x): return round(float(x),5) if pd.notna(x) and math.isfinite(float(x)) else None
    return {'schema_version':1,'status':'ok','data_status':mode,'generated_utc':today.isoformat(),'mzm_generated_utc':mzm_generated,'frequency':'quarterly','units':'percent year over year','common_latest':str(complete.index.max()),'latest_by_series':latest,'history':[{'quarter':str(i),**{k:num(x) for k,x in row.items()}} for i,row in g.iterrows() if row.notna().any()], 'methodology':{'mzm':'Existing Foreign-adjusted MZM proxy, quarter-end; historical MZMSL prior to 1982','fili':'Transaction chain: I(t)=I(t-1)*(1+F(t)/A(t-1)); 1967Q1=100. Fed Z.1 securities brokers and dealers','gdp':'Nominal GDP, SAAR','m2':'M2SL, seasonally adjusted, quarter-end','timing':'Observation quarters, latest revised data, not real-time vintages. No forward fill. Partial quarter excluded.'},'sources':{'mzm':'data/mzm_ratio.json',**CODES}}

def selftest():
    i=pd.period_range(BASE,periods=6,freq='Q');a=pd.Series([100,120,130,140,150,160],i);f=pd.Series([0,10,12,0,-7,0],i)
    assert np.allclose(chain(a,f),[100,110,121,121,114.95,114.95])
    try: chain(a,f.drop(i[2]))
    except ValueError: pass
    else: raise AssertionError('Gap not detected')

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',nargs=2,metavar=('MZM_CSV','FILI_CSV'));p.add_argument('--out',type=Path,default=ROOT/'data'/'liquidity_cycle.json');args=p.parse_args();selftest()
    if args.snapshot:
        m=pd.read_csv(args.snapshot[0]).set_index('quarter');f=pd.read_csv(args.snapshot[1]).set_index('quarter');d=pd.DataFrame({'mzm':m.FA_MZM,'fili':f.FILI_T,'gdp':f.gdp,'m2':f.m2});d.index=pd.PeriodIndex(d.index,freq='Q');payload=build(d,mode='research_snapshot')
    else:
        m,stamp=from_mzm_json(ROOT/'data'/'mzm_ratio.json');a=quarter(fred(CODES['assets']));f=quarter(fred(CODES['flows']));i=chain(a,f);d=pd.DataFrame({'mzm':m,'fili':i,'gdp':quarter(fred(CODES['GDP'])),'m2':quarter(fred(CODES['M2']),monthly=True)});payload=build(d,stamp)
        # Refuse silently regressing the common data endpoint on a failed/partial source.
        if args.out.exists():
            old=json.loads(args.out.read_text());prev=old.get('common_latest')
            if prev and pd.Period(payload['common_latest'],freq='Q')<pd.Period(prev,freq='Q'): raise ValueError('Common endpoint regressed; preserving previous JSON')
    args.out.parent.mkdir(parents=True,exist_ok=True);tmp=args.out.with_suffix('.tmp');tmp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n',encoding='utf-8');tmp.replace(args.out)
    print('SELFTEST OK; common latest:',payload['common_latest']);print('Latest by series:',payload['latest_by_series']);print([r for r in payload['history'] if r['quarter']==payload['common_latest']][0])

if __name__=='__main__':main()
