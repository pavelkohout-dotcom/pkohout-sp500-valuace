"""Monthly inflation-only Taylor gap; PCEPI and FEDFUNDS aligned by month."""
import json, math, os, time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

def observations(payload):
    result={}
    for row in payload.get('observations',[]):
        if row.get('value') in (None,'','.'): continue
        day=date.fromisoformat(row['date'])
        value=float(row['value'])
        if not math.isfinite(value) or day>datetime.now(timezone.utc).date(): raise ValueError('Invalid observation')
        month=day.strftime('%Y-%m')
        if month in result: raise ValueError('Duplicate month')
        result[month]=value
    return result

def calculate(pce,rates):
    if not pce or not rates: raise ValueError('Missing series')
    month=max(pce)
    prior=str(int(month[:4])-1)+month[4:]
    if month not in rates or prior not in pce: raise ValueError('Latest PCE month lacks matching rate or year-ago PCE')
    current,base,rate=pce[month],pce[prior],rates[month]
    if not all(math.isfinite(v) for v in (current,base,rate)) or current<=0 or base<=0: raise ValueError('Invalid inputs')
    inflation=(current/base-1)*100
    prescribed=1+1.5*inflation
    return {'schema_version':1,'date':month+'-01','base_date':prior+'-01','pce_index':current,'pce_index_year_ago':base,'inflation_yoy':inflation,'fedfunds':rate,'taylor_rate':prescribed,'value':rate-prescribed,'neutral_real_rate':2,'inflation_target':2,'output_gap_assumption':0,'sources':{'inflation':'https://fred.stlouisfed.org/series/PCEPI','rate':'https://fred.stlouisfed.org/series/FEDFUNDS'}}

def fetch_series(series):
    key=os.environ.get('FRED_API_KEY')
    if not key: raise RuntimeError('FRED_API_KEY secret is missing')
    url='https://api.stlouisfed.org/fred/series/observations?'+urlencode({'api_key':key,'series_id':series,'file_type':'json','sort_order':'desc','limit':36})
    for attempt in range(3):
        try:
            with urlopen(url,timeout=30) as r: return observations(json.load(r))
        except Exception:
            if attempt==2: raise RuntimeError('FRED download failed for '+series) from None
            time.sleep(2**attempt)

def publish(payload,path):
    if path.exists():
        old=json.loads(path.read_text())
        if old['date']>payload['date']: raise ValueError('Older observation rejected')
        if all(old.get(k)==v for k,v in payload.items()): return
    payload=dict(payload,generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    path.parent.mkdir(exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n');temp.replace(path)

if __name__=='__main__':
    payload=calculate(fetch_series('PCEPI'),fetch_series('FEDFUNDS'))
    publish(payload,Path(__file__).resolve().parent/'data'/'taylor_gap.json')
    print(f"Taylor gap: {payload['value']:.4f} pp ({payload['date'][:7]})")
