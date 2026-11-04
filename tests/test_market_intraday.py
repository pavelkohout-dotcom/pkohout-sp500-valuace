import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import update_vix_intraday as feed
import update_market_intraday as market

class MarketTests(unittest.TestCase):
    def test_sp500_validation(self):
        now=datetime(2026,11,4,18,tzinfo=timezone.utc)
        d={'chart':{'result':[{'meta':{'symbol':'^GSPC','instrumentType':'INDEX','regularMarketPrice':7700,'regularMarketTime':now.timestamp()-60}}]}}
        q=feed.parse_quote(d,now,'^GSPC')
        self.assertEqual(q['series_id'],'SP500');self.assertEqual(q['symbol'],'^GSPC')
        self.assertEqual(feed.validate_saved(q,now,'^GSPC')['quote_time'],q['quote_time'])
        with self.assertRaises(ValueError):feed.parse_quote(d,now,'^VIX')
    def test_window(self):
        for stamp,want in [('2026-11-04T18:00:00+00:00',True),('2026-11-04T22:35:00+00:00',False),('2026-11-07T18:00:00+00:00',False)]:
            self.assertEqual(market.active_window(datetime.fromisoformat(stamp)),want)
    def test_watch_collects_more_than_once(self):
        with patch.object(market,'collect') as collect,patch.object(market,'push') as push,patch.object(market.time,'sleep') as sleep,patch.object(market,'active_window',side_effect=[True,False]):
            market.run(watch=True,publish=True)
            self.assertEqual(collect.call_count,2);self.assertEqual(push.call_count,2);sleep.assert_called_once()
    def test_one_shot(self):
        with patch.object(market,'collect') as collect,patch.object(market,'push') as push:
            market.run();collect.assert_called_once();push.assert_not_called()

if __name__=='__main__':unittest.main()
