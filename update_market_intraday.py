"""Poll both indices in a bounded Actions job instead of relying on each cron tick."""
import argparse
import json
from zoneinfo import ZoneInfo
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import update_vix_intraday as feed

ROOT = Path(__file__).resolve().parent

INTERVAL_SECONDS = 30 * 60
CALENDAR = json.loads((ROOT / 'data/market_calendar.json').read_text())

def active_window(now):
    local = now.astimezone(ZoneInfo('America/New_York'))
    day = local.date().isoformat()
    if not CALENDAR['valid_from'] <= day <= CALENDAR['valid_through']:
        raise RuntimeError('Market calendar expired; update data/market_calendar.json')
    close = 13 * 60 if day in CALENDAR['early_closes'] else 16 * 60
    # One hour after close includes the delayed final VIX observation.
    return local.weekday() < 5 and day not in CALENDAR['holidays'] and 570 <= local.hour * 60 + local.minute <= close + 60

def due(now):
    for name in ['vix_intraday.json', 'sp500_intraday.json']:
        try:
            checked = datetime.fromisoformat(json.loads((ROOT / 'data' / name).read_text())['checked_at'])
            age = (now - checked).total_seconds()
            if age < 0 or age >= INTERVAL_SECONDS:
                return True
        except (OSError, ValueError, KeyError, TypeError):
            return True
    return False

def collect():
    for symbol, name in [('^VIX', 'vix_intraday.json'), ('^GSPC', 'sp500_intraday.json')]:
        try:
            quote = feed.download(symbol=symbol)
        except RuntimeError:
            quote = None
        data = feed.publish(quote, ROOT / 'data' / name, symbol=symbol)
        print(symbol, data.get('value'), data.get('quote_time'), data['fetch_status'], flush=True)

def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, capture_output=True, text=True)

def push():
    git('add', 'data/vix_intraday.json', 'data/sp500_intraday.json')
    if not git('diff', '--cached', '--name-only').stdout.strip():
        return
    git('commit', '-m', 'Refresh intraday VIX and S&P 500')
    for attempt in range(3):
        try:
            git('pull', '--rebase', 'origin', 'main')
            git('push', 'origin', 'HEAD:main')
            return
        except subprocess.CalledProcessError:
            # Never discard competing changes. A real rebase conflict fails the job.
            if (ROOT / '.git/rebase-merge').exists() or (ROOT / '.git/rebase-apply').exists():
                raise
            if attempt == 2:
                raise
            time.sleep(5)

def run(watch=False, publish=False, duration_minutes=300):
    deadline = time.monotonic() + duration_minutes * 60
    while True:
        now = datetime.now(timezone.utc)
        if not watch or (active_window(now) and due(now)):
            collect()
            if publish:
                push()
        remaining = deadline - time.monotonic()
        if not watch or remaining <= 0:
            return
        # Stay alive overnight/weekends so the next session does not depend on cron.
        time.sleep(min(60, remaining))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--duration-minutes', type=int, default=300, choices=range(1, 301))
    args = parser.parse_args()
    run(args.watch, args.publish, args.duration_minutes)
