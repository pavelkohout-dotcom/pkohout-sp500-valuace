import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import update_vix_intraday as vix

NOW = datetime(2026, 11, 3, 16, 0, tzinfo=timezone.utc)
def fixture(value=20.3, stamp=None, symbol='^VIX'):
    return {'chart': {'result': [{'meta': {'symbol': symbol, 'instrumentType': 'INDEX',
      'regularMarketPrice': value, 'regularMarketTime': stamp if stamp is not None else NOW.timestamp()-900}}]}}

class VixTests(unittest.TestCase):
    def test_quote_time_not_fetch_time(self):
        q=vix.parse_quote(fixture(), NOW)
        self.assertEqual(q['quote_time'], '2026-11-03T15:45:00+00:00')
        self.assertEqual(q['date'], '2026-11-03')
        self.assertEqual(q['delay_minutes'], 15)
    def test_reject_bad_price_symbol_time(self):
        for value in [None, True, 0, -1, float('nan'), float('inf'), '20']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                vix.parse_quote(fixture(value=value), NOW)
        for stamp in [0, -1, True, '123', NOW.timestamp()+120]:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                vix.parse_quote(fixture(stamp=stamp), NOW)
        with self.assertRaises(ValueError): vix.parse_quote(fixture(symbol='VIXY'), NOW)
    def test_ny_date_and_dst(self):
        q=vix.parse_quote(fixture(stamp=datetime(2026,11,3,1,tzinfo=timezone.utc).timestamp()),NOW)
        self.assertEqual(q['date'],'2026-11-02')
    def test_failure_and_regression_preserve_observation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'vix.json'
            quote=vix.parse_quote(fixture(),NOW)
            vix.publish(quote,path,NOW)
            for candidate in [None,vix.parse_quote(fixture(stamp=NOW.timestamp()-3600),NOW)]:
                result=vix.publish(candidate,path,NOW+timedelta(minutes=5))
                self.assertEqual(result['quote_time'],quote['quote_time'])
                self.assertEqual(result['fetch_status'],'retained')
                self.assertEqual(json.loads(path.read_text())['value'],20.3)
    def test_same_value_new_time_advances(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'vix.json'
            vix.publish(vix.parse_quote(fixture(),NOW),path,NOW)
            result=vix.publish(vix.parse_quote(fixture(stamp=NOW.timestamp()-600),NOW),path,NOW)
            self.assertEqual(result['quote_time'],'2026-11-03T15:50:00+00:00')
    def test_missing_or_corrupt_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'vix.json'
            for content in [None,'broken','{"value": 10}']:
                if content is not None:path.write_text(content)
                result=vix.publish(None,path,NOW)
                self.assertEqual(result['fetch_status'],'unavailable')
                self.assertIsNone(result['value'])
    def test_both_hosts_fail(self):
        with patch.object(vix,'urlopen',side_effect=OSError('offline')) as request:
            with self.assertRaises(RuntimeError):vix.download(NOW)
            self.assertEqual(request.call_count,2)

if __name__=='__main__':unittest.main()
