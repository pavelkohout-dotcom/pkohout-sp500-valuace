#!/usr/bin/env python3
"""Publish the latest valid FRED T10Y2Y close; retain the existing file on failure."""
import json
import math
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'data' / 't10y2y.json'

def parse_observations(payload):
    points = []
    for row in payload.get('observations', []):
        if row.get('value') in (None, '', '.'):
            continue
        value = float(row['value'])
        day = date.fromisoformat(row['date'])
        if not math.isfinite(value) or day > datetime.now(timezone.utc).date():
            raise ValueError('Invalid yield spread observation')
        points.append((day, value))
    if not points:
        raise ValueError('No valid yield spread observations')
    day, value = max(points)
    return {'series_id': 'T10Y2Y', 'value': value, 'date': day.isoformat(),
            'source': 'https://fred.stlouisfed.org/series/T10Y2Y',
            'attribution': 'Federal Reserve Bank of St. Louis (FRED)',
            'frequency': 'Daily', 'units': 'Percent'}

def download():
    key = os.environ.get('FRED_API_KEY')
    if not key:
        raise RuntimeError('Configure the FRED_API_KEY GitHub Actions secret')
    url = 'https://api.stlouisfed.org/fred/series/observations?' + urlencode({
        'api_key': key, 'series_id': 'T10Y2Y', 'file_type': 'json',
        'sort_order': 'desc', 'limit': 30})
    for attempt in range(3):
        try:
            with urlopen(url, timeout=30) as response:
                return parse_observations(json.load(response))
        except Exception:
            if attempt == 2:
                # Do not print request URLs: they contain the API key.
                raise RuntimeError('FRED T10Y2Y download failed; existing JSON retained') from None
            time.sleep(2 ** attempt)

def publish(payload, output=OUTPUT):
    if output.exists():
        old = json.loads(output.read_text(encoding='utf-8'))
        if old['date'] > payload['date']:
            raise ValueError('Older yield spread observation rejected')
        if old.get('value') == payload['value'] and old.get('date') == payload['date']:
            return False
    payload = dict(payload, generated_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(output)
    return True

if __name__ == '__main__':
    data = download()
    publish(data)
    print(f"T10Y2Y: {data['value']} ({data['date']})")
