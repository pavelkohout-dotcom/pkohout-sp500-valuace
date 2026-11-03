#!/usr/bin/env python3
"""Best-effort Yahoo ^VIX spot quotes. Never relabel a fetch time as quote time."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'data/vix_intraday.json'
SOURCE = 'https://finance.yahoo.com/quote/%5EVIX/'
NY = ZoneInfo('America/New_York')


def parse_quote(payload, now=None):
    now = now or datetime.now(timezone.utc)
    chart = payload['chart']
    if chart.get('error'):
        raise ValueError('Provider error')
    meta = chart['result'][0]['meta']
    if meta.get('symbol') != '^VIX' or meta.get('instrumentType') != 'INDEX':
        raise ValueError('Expected VIX spot index')
    value, stamp = meta.get('regularMarketPrice'), meta.get('regularMarketTime')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Invalid VIX value')
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp) or stamp <= 0:
        raise ValueError('Missing quote timestamp')
    quoted = datetime.fromtimestamp(stamp, timezone.utc)
    if (quoted - now).total_seconds() > 60:
        raise ValueError('Future quote timestamp')
    return {'schema_version': 1, 'series_id': 'VIX', 'symbol': '^VIX',
            'value': value, 'date': quoted.astimezone(NY).date().isoformat(),
            'quote_time': quoted.isoformat(timespec='seconds'),
            'source': SOURCE, 'provider': 'Yahoo Finance / Cboe',
            'frequency': 'intraday', 'delay_minutes': 15}


def download(now=None):
    # Unofficial endpoint: may throttle or change. Daily FRED remains independent.
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        try:
            request = Request(f'https://{host}/v8/finance/chart/%5EVIX?interval=1m&range=1d',
                              headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
            with urlopen(request, timeout=15) as response:
                return parse_quote(json.load(response), now)
        except Exception:
            continue
    raise RuntimeError('Yahoo VIX unavailable; retaining last observation')


def validate_saved(data, now):
    if data.get('series_id') != 'VIX' or data.get('frequency') != 'intraday':
        raise ValueError('Invalid saved series')
    stamp = datetime.fromisoformat(data['quote_time'].replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Missing timezone')
    return parse_quote({'chart': {'result': [{'meta': {'symbol': '^VIX',
        'instrumentType': 'INDEX', 'regularMarketPrice': data['value'],
        'regularMarketTime': stamp.timestamp()}}]}}, now)


def publish(quote, output=OUTPUT, now=None):
    now = now or datetime.now(timezone.utc)
    old = None
    try:
        old = validate_saved(json.loads(output.read_text()), now)
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        pass
    if quote is not None:
        quote = validate_saved(quote, now)
    if old and (quote is None or old['quote_time'] > quote['quote_time']):
        quote = old
        status = 'retained'
    else:
        status = 'ok' if quote else 'unavailable'
    payload = dict(quote or {'schema_version': 1, 'series_id': 'VIX', 'value': None},
                   fetch_status=status, checked_at=now.isoformat(timespec='seconds'))
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
    temp.replace(output)
    return payload


def main():
    try:
        quote = download()
    except RuntimeError as exc:
        print(str(exc))
        quote = None
    result = publish(quote)
    print(f"VIX: {result['fetch_status']}; quote time: {result.get('quote_time', 'unavailable')}")


if __name__ == '__main__':
    main()
