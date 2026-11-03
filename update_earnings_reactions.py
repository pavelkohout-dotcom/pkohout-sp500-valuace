"""Observed EPS beats followed by first-session price declines; separate from FactSet."""
import csv
import io
import json
import math
import time
import warnings
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import exchange_calendars as xc
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
UNIVERSE_URL = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'
NY = ZoneInfo('America/New_York')


def get_json(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def season_window(quarter, today):
    year, q = quarter.split('-Q')
    year, q = int(year), int(q)
    if q not in (1, 2, 3, 4):
        raise ValueError('Invalid quarter')
    start = date(year + (q == 4), q * 3 % 12 + 1, 1)
    end = date(start.year + (start.month == 10), (start.month + 2) % 12 + 1, 1) - timedelta(days=1)
    if today < start:
        raise ValueError('Reporting season has not started')
    return start, min(today, end)


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def reaction_sessions(released, calendar):
    """First regular session closing strictly after release, including holidays/early close."""
    stamp = pd.Timestamp(released)
    if stamp.tzinfo is None:
        raise ValueError('Release requires timezone')
    day = stamp.tz_convert('America/New_York').date()
    for session in calendar.sessions_in_range(day, day + timedelta(days=10)):
        if calendar.session_close(session) > stamp:
            return calendar.previous_session(session), session
    raise ValueError('No reaction session')


def price_reaction(payload, symbol, before, after):
    result = payload['chart']['result'][0]
    if result['meta']['symbol'] != symbol:
        raise ValueError('Wrong price symbol')
    closes = result['indicators']['quote'][0]['close']
    stamps = result['timestamp']
    if len(stamps) != len(closes):
        raise ValueError('Mismatched prices')
    points = {datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date().isoformat(): number(c)
              for t, c in zip(stamps, closes)}
    for split in result.get('events', {}).get('splits', {}).values():
        day = datetime.fromtimestamp(split['date'], timezone.utc).astimezone(NY).date().isoformat()
        if before < day <= after:
            raise ValueError('Split during reaction window')
    a, b = points.get(before), points.get(after)
    if a is None or b is None or a <= 0 or b <= 0:
        raise ValueError('Missing exact session closing price')
    return {'before_date': before, 'after_date': after, 'before_close': a,
            'after_close': b, 'change_pct': (b / a - 1) * 100}


def universe():
    with urlopen(Request(UNIVERSE_URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode())))
    if not 450 <= len(rows) <= 550 or any(not r.get('CIK') for r in rows):
        raise ValueError('Unexpected constituent list')
    return {r['Symbol'].replace('.', '-'): r for r in rows}


def calendar_rows(start, end):
    service = yf.Calendars(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
    records, seen_pages = [], set()
    for offset in range(0, 10000, 100):
        frame = service.get_earnings_calendar(filter_most_active=False, limit=100, offset=offset)
        signature = frame.to_json(date_format='iso', orient='split')
        if signature in seen_pages:
            raise ValueError('Repeated earnings page; refusing incomplete scan')
        seen_pages.add(signature)
        records.extend(frame.reset_index().to_dict('records'))
        if len(frame) < 100:
            return records
        time.sleep(.25)
    raise ValueError('Earnings pagination limit exceeded')


def normalize(records, members, start, end):
    events = {}
    for row in records:
        symbol = str(row.get('Symbol', '')).replace('.', '-')
        if symbol not in members:
            continue
        stamp = pd.Timestamp(row.get('Event Start Date'))
        if pd.isna(stamp) or stamp.tzinfo is None:
            continue
        day = stamp.tz_convert('America/New_York').date()
        if not start <= day <= end:
            continue
        actual, estimate = number(row.get('Reported EPS')), number(row.get('EPS Estimate'))
        if actual is None or estimate is None:
            continue
        # Count issuers, not share classes (e.g. GOOG + GOOGL).
        key = members[symbol]['CIK'] + ':' + day.isoformat()
        event = {'id': key, 'symbol': symbol, 'company': members[symbol]['Security'],
                 'reported_at': stamp.isoformat(), 'report_date': day.isoformat(),
                 'timing': str(row.get('Timing', '')), 'eps_actual': actual,
                 'eps_estimate': estimate, 'beat': actual > estimate,
                 'earnings_source': 'https://finance.yahoo.com/calendar/earnings?day=' + day.isoformat(),
                 'price_source': 'https://finance.yahoo.com/quote/' + quote(symbol, safe='') + '/history/'}
        old = events.get(key)
        if old:
            if any(old[k] != event[k] for k in ('eps_actual', 'eps_estimate', 'reported_at', 'timing')):
                old['conflict'] = True
            continue
        events[key] = event
    return list(events.values())


def build(events, now, price_loader, calendar):
    beats = []
    for event in events:
        if not event['beat']:
            continue
        row = dict(event)
        row['status'] = 'unverified_time'
        if row.get('conflict'):
            row['status'] = 'conflicting_source'
        elif row['timing'] == 'TAS':  # Yahoo: time supplied; TNS timestamps are placeholders.
            try:
                before, after = reaction_sessions(row['reported_at'], calendar)
                if calendar.session_close(after) + pd.Timedelta(minutes=30) > pd.Timestamp(now):
                    row['status'] = 'pending_close'
                else:
                    symbol = row['symbol']
                    payload = price_loader(symbol, before, after)
                    row.update(price_reaction(payload, symbol, before.date().isoformat(), after.date().isoformat()))
                    row['status'] = 'measured'
            except Exception:
                row['status'] = 'price_unavailable'
        beats.append(row)
    measured = [r for r in beats if r['status'] == 'measured']
    declines = sorted([r for r in measured if r['change_pct'] < 0], key=lambda r: r['change_pct'])
    return beats, {'reported_with_eps': len(events), 'beats': len(beats), 'measured_beats': len(measured),
                   'declined': len(declines), 'unmeasured_beats': len(beats) - len(measured)}


def load_price(symbol, before, after):
    start = int((before - pd.Timedelta(days=2)).timestamp())
    end = int((after + pd.Timedelta(days=2)).timestamp())
    return get_json(f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe="")}?interval=1d&period1={start}&period2={end}&events=splits')


def main():
    warnings.filterwarnings('ignore', category=FutureWarning)
    yf.set_tz_cache_location(str(ROOT / '.cache/earnings-yahoo'))
    now = datetime.now(timezone.utc)
    scorecard = json.loads((ROOT / 'data/earnings_beat_rate.json').read_text())
    quarter = scorecard['quarter']
    start, end = season_window(quarter, now.astimezone(NY).date())
    members = universe()
    records = calendar_rows(start, end)
    events = normalize(records, members, start, end)
    if not events:
        raise RuntimeError('No verified EPS events; previous snapshot retained')
    beats, counts = build(events, now, load_price, xc.get_calendar('XNYS'))
    if not counts['measured_beats']:
        raise RuntimeError('No measurable reactions; previous snapshot retained')
    payload = {'schema_version': 1, 'metric': 'eps_beat_first_close_reaction', 'quarter': quarter,
        'window_start': start.isoformat(), 'window_end': end.isoformat(),
        'generated_utc': now.isoformat(timespec='seconds'), 'status': 'partial',
        'provider': 'Yahoo Finance', 'universe_source': UNIVERSE_URL,
        'universe_asof': now.date().isoformat(), 'universe_symbols': len(members),
        'method': 'first_regular_close_after_release_vs_previous_close',
        'counts': counts, 'events': beats}
    output = ROOT / 'data/earnings_reactions.json'
    tmp = output.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(output)
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
