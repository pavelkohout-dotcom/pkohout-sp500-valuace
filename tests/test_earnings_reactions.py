import unittest
from datetime import date, datetime, timezone
import pandas as pd
import exchange_calendars as xc
from update_earnings_reactions import season_window, reaction_sessions, price_reaction, normalize, build

class ReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.cal=xc.get_calendar('XNYS')
    def pair(self,t):return tuple(s.date().isoformat() for s in reaction_sessions(t,self.cal))
    def test_before_open(self):self.assertEqual(self.pair('2026-10-29T07:00:00-04:00'),('2026-10-28','2026-10-29'))
    def test_after_close(self):self.assertEqual(self.pair('2026-10-29T16:01:00-04:00'),('2026-10-29','2026-10-30'))
    def test_weekend_dst(self):self.assertEqual(self.pair('2026-10-30T16:05:00-04:00'),('2026-10-30','2026-11-02'))
    def test_early_close(self):self.assertEqual(self.pair('2026-11-27T13:05:00-05:00'),('2026-11-27','2026-11-30'))
    def test_holiday(self):self.assertEqual(self.pair('2026-11-26T08:00:00-05:00'),('2026-11-25','2026-11-27'))
    def test_window_roll(self):
        self.assertEqual(season_window('2026-Q4',date(2027,1,15)),(date(2027,1,1),date(2027,1,15)))
        self.assertEqual(season_window('2026-Q3',date(2027,1,15))[1],date(2026,12,31))
    def price(self,closes=(100,95)):
        return {'chart':{'result':[{'meta':{'symbol':'ABC'},'timestamp':[int(pd.Timestamp(s).timestamp()) for s in ['2026-10-28T13:30:00Z','2026-10-29T13:30:00Z']], 'indicators':{'quote':[{'close':list(closes)}]}}]}}
    def test_price_return(self):
        r=price_reaction(self.price(),'ABC','2026-10-28','2026-10-29');self.assertAlmostEqual(r['change_pct'],-5)
        for closes in [(None,95),(100,0)]:
            with self.assertRaises(ValueError):price_reaction(self.price(closes),'ABC','2026-10-28','2026-10-29')
        with self.assertRaises(ValueError):price_reaction(self.price(),'ABC','2026-10-27','2026-10-29')
    def test_split_excluded(self):
        p=self.price();p['chart']['result'][0]['events']={'splits':{'x':{'date':int(pd.Timestamp('2026-10-29T13:30Z').timestamp())}}}
        with self.assertRaises(ValueError):price_reaction(p,'ABC','2026-10-28','2026-10-29')
    def test_issuer_dedup_and_negative_eps(self):
        members={'ABC':{'CIK':'1','Security':'ABC'},'DEF':{'CIK':'1','Security':'ABC'}}
        row={'Symbol':'ABC','Event Start Date':pd.Timestamp('2026-10-29T07:00-04:00'),'Timing':'TAS','Reported EPS':-.5,'EPS Estimate':-1}
        events=normalize([row,dict(row,Symbol='DEF')],members,date(2026,10,1),date(2026,11,3))
        self.assertEqual(len(events),1);self.assertTrue(events[0]['beat'])
        conflicts=normalize([row,dict(row,Symbol='DEF',**{'Reported EPS':2})],members,date(2026,10,1),date(2026,11,3))
        self.assertTrue(conflicts[0]['conflict'])
    def test_pending_unknown_and_measured(self):
        e={'id':'1','symbol':'ABC','beat':True,'timing':'TAS','reported_at':'2026-10-29T11:00Z'}
        now=datetime(2026,10,29,19,tzinfo=timezone.utc)
        rows,c=build([e,dict(e,id='2',timing='TNS')],now,lambda *a:self.price(),self.cal)
        self.assertEqual([r['status'] for r in rows],['pending_close','unverified_time']);self.assertEqual(c['declined'],0)
        rows,c=build([e],datetime(2026,10,30,tzinfo=timezone.utc),lambda *a:self.price(),self.cal)
        self.assertEqual(c['declined'],1);self.assertEqual(c['measured_beats'],1)

if __name__=='__main__':unittest.main()
