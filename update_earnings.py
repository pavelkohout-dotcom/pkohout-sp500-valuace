"""Conservative weekly extraction of the FactSet first-page EPS scorecard."""
import io,json,re,time
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from urllib.request import urlopen
from pypdf import PdfReader
BASE='https://advantage.factset.com/hubfs/Website/Resources%20Section/Research%20Desk/Earnings%20Insight/'
PATTERN=r'For Q\s*(\d) (\d{4}) \(with ((?:over |more than |>)?\d+)% (?:of S&P 500 companies|of the companies in the S&P 500|S&P 500 companies) reporting actual results\), (\d+)% of S&P 500 companies (?:have|has) reported a positive EPS surprise'

def extract(data,day,url):
 text=' '.join(PdfReader(io.BytesIO(data)).pages[0].extract_text().split())
 expected=day.strftime('%B')+' '+str(day.day)+', '+str(day.year)
 if expected not in text:raise ValueError('Report date mismatch')
 matches=list(re.finditer(PATTERN,text))
 if len(matches)!=1:raise ValueError('Missing or ambiguous first-page scorecard')
 m=matches[0];q=int(m[1]);year=int(m[2]);coverage=int(re.search(r'\d+',m[3])[0]);value=int(m[4])
 if not 1<=q<=4 or not 0<coverage<=100 or not 0<=value<=100:raise ValueError('Invalid scorecard')
 start=date(year,3*q-2,1)
 if not start<=day or (day-start).days>240:raise ValueError('Quarter/date mismatch')
 return {'quarter':f'{year}-Q{q}','value':value,'reporting_percent':coverage,'reporting_relation':'gt' if m[3].startswith(('over','more','>')) else 'eq','report_date':day.isoformat(),'source':url,'source_page':1,'status':'complete' if coverage==100 else 'near_complete' if coverage>=95 else 'partial'}

def discover(today):
 friday=today-timedelta(days=(today.weekday()-4)%7)
 for week in range(3):
  for shift in [0,1]:
   day=friday-timedelta(days=7*week+shift)
   for suffix in ['','A','B']:
    url=BASE+'EarningsInsight_'+day.strftime('%m%d%y')+suffix+'.pdf'
    try:
     with urlopen(url,timeout=15) as r:data=r.read(15000000)
     return extract(data,day,url)
    except Exception:pass
 raise RuntimeError('No verifiable recent FactSet scorecard; existing data retained')

def merge(payload,row):
 old=payload
 if row['report_date']<old['report_date'] or row['quarter']<old['quarter']:raise ValueError('Older scorecard rejected')
 if row['quarter']==old['quarter'] and row['reporting_percent']<old['reporting_percent']:raise ValueError('Coverage regression')
 return dict(payload,**row)

if __name__=='__main__':
 path=Path(__file__).resolve().parent/'data'/'earnings_beat_rate.json'
 original=json.loads(path.read_text());row=discover(datetime.now(timezone.utc).date());updated=merge(original,row)
 if updated!=original:
  updated['generated_utc']=datetime.now(timezone.utc).isoformat(timespec='seconds')
  temp=path.with_suffix('.tmp');temp.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
 print(f"EPS beat rate: {row['value']}%; {row['quarter']}; reporting {row['reporting_percent']}%; report {row['report_date']}")
