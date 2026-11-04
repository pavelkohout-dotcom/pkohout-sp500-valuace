"""Poll both indices in a bounded Actions job instead of relying on each cron tick."""
import argparse
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import update_vix_intraday as feed

ROOT = Path(__file__).resolve().parent

def active_window(now):
    return now.weekday() < 5 and (12, 0) <= (now.hour, now.minute) < (22, 35)

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

def run(watch=False, publish=False):
    deadline = time.monotonic() + 330 * 60
    while True:
        started = time.monotonic()
        collect()
        if publish:
            push()
        now = datetime.now(timezone.utc)
        if not watch or not active_window(now) or time.monotonic() + 300 >= deadline:
            return
        time.sleep(max(1, 300 - (time.monotonic() - started)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    run(args.watch, args.publish)
