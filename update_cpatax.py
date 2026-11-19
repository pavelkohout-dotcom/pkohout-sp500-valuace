#!/usr/bin/env python3
"""Automaticka aktualizace CPATAX (FRED) pro veřejný valuační graf."""
import csv, datetime as dt, io, json, pathlib, time, urllib.request

URLS=[
"https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPATAX",
"https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPATAX&cosd=1947-01-01",
]
OUT=pathlib.Path(__file__).resolve().parent/"data"/"cpatax.json"

def parse_csv(text):
    reader=csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise ValueError("FRED nevratil CSV")
    datecol="DATE" if "DATE" in reader.fieldnames else "observation_date"
    if datecol not in reader.fieldnames or "CPATAX" not in reader.fieldnames:
        raise ValueError("Chybi sloupce DATE a CPATAX")
    rows=[]
    for r in reader:
        x=(r.get("CPATAX") or "").strip()
        if not x or x==".":
            continue
        d=dt.date.fromisoformat(r[datecol].strip())
        if d.month not in (1,4,7,10) or d.day!=1:
            raise ValueError("Neplatna ctvrtletni data")
        v=float(x)
        if not 0<v<100000:
            raise ValueError("Neplatna hodnota")
        rows.append({"date":d.isoformat(),"value":v})
    if len(rows)<300 or rows[0]["date"]>"1947-01-01":
        raise ValueError("Neuplna historie")
    if any(a["date"]>=b["date"] for a,b in zip(rows,rows[1:])):
        raise ValueError("Nesestupna nebo duplicitni data")
    if rows[-1]["date"]>(dt.date.today()+dt.timedelta(days=100)).isoformat():
        raise ValueError("Budouci datum")
    return rows

def download():
    errs=[]
    for url in URLS:
        for attempt in range(3):
            try:
                request=urllib.request.Request(url,headers={
                    "User-Agent":"Mozilla/5.0 (compatible; CPATAXUpdater/1.0)",
                    "Accept":"text/csv,text/plain,*/*"})
                with urllib.request.urlopen(request,timeout=35) as response:
                    text=response.read(3000000).decode("utf-8-sig")
                return parse_csv(text)
            except Exception as e:
                errs.append(str(e))
                time.sleep(attempt+1)
    raise RuntimeError("Stazeni CPATAX selhalo: "+"; ".join(errs[-3:]))

def main():
    rows=download()
    if OUT.exists():
        old=json.loads(OUT.read_text(encoding="utf-8")).get("history",[])
        if old and rows[-1]["date"]<old[-1]["date"]:
            raise ValueError("FRED ma starsi data nez posledni uspesny beh")
        if old==rows:
            print("Beze zmeny")
            return
    doc={
        "schema_version":1,"status":"ok","series":"CPATAX",
        "source":"FRED / U.S. Bureau of Economic Analysis",
        "units":"Billions of USD, seasonally adjusted annual rate",
        "generated_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "latest_observation_date":rows[-1]["date"],
        "latest_observation_value":rows[-1]["value"],
        "history":rows
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Vygenerovano",len(rows),"pozorovani; posledni",rows[-1])

if __name__=="__main__":
    main()
