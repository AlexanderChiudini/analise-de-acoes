import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models import DEFAULTS, calculate, validate
from providers import parse_investidor10
import server

class ModelTests(unittest.TestCase):
    def test_user_spreadsheet(self):
        data = dict(DEFAULTS, price=47.99, dy=3.85, dps=1.85, eps=1.49, bvps=4.49, growth=5, ipca=4.9, desired_yield=8, safety_margin=15)
        a = calculate(data)
        self.assertAlmostEqual(a['values']['bazin'], 23.125)
        self.assertAlmostEqual(a['values']['graham'], math.sqrt(22.5*1.49*4.49))
        self.assertAlmostEqual(a['values']['gordon'], 1.85*1.05/.089)
        self.assertEqual(a['final_signal'], 'CARA')
        self.assertAlmostEqual(a['values']['safe_average'], sum(a['values'][k] for k in ('bazin','graham','gordon'))/3*.85)

    def test_invalid_models_do_not_emit_signal(self):
        a = calculate(dict(DEFAULTS, price=20, eps=-1, bvps=4, dps=1, ipca=4))
        self.assertIsNone(a['values']['graham'])
        self.assertIsNone(a['values']['safe_average'])
        self.assertEqual(a['final_signal'], 'SEM DADOS')
        self.assertIsNone(calculate(dict(DEFAULTS, ipca=4, growth=13, dps=1))['values']['gordon'])

    def test_missing_and_zero(self):
        self.assertEqual(calculate(DEFAULTS)['signal'], 'SEM DADOS')
        a = calculate(dict(DEFAULTS, price=10, eps=1, bvps=10, dps=0, ipca=4))
        self.assertEqual(a['values']['bazin'], 0)
        self.assertEqual(a['potential']['conservative'], -100)

    def test_compound_and_dcf(self):
        a = calculate(dict(DEFAULTS, ipca=5, rate_mode='compound', dps=1, fcf_per_share=2))
        self.assertAlmostEqual(a['indicators']['discount_rate'], 14.45)
        self.assertGreater(a['values']['dcf'], 0)

    def test_validation(self):
        for bad in [{'price':0}, {'price':-1}, {'eps':float('nan')}, {'dcf_years':1.5}, {'safety_margin':100}, {'growth':100}, {'quality':[]}]:
            with self.assertRaises(ValueError):
                validate(bad)
        self.assertEqual(validate({'eps':-2})['eps'], -2)

    def test_sqlite_history_and_parameterized_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = server.DB
            try:
                server.DB = Path(tmp)/'test.sqlite3'
                server.init()
                asset = server.get_asset('WEGE3')
                asset['data'].update(price=47.99, notes="tese ' com aspas")
                server.save_asset(asset)
                server.save_asset(asset)
                self.assertEqual(server.get_asset('WEGE3')['data']['notes'], "tese ' com aspas")
                with server.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM analyses').fetchone()[0], 2)
                with self.assertRaises(ValueError):
                    server.ticker_value("WEGE3'; DROP TABLE assets")
            finally:
                server.DB = original

    def test_real_provider_fixture(self):
        fixture = Path(__file__).resolve().parents[1]/'investidor10-sample.html'
        if not fixture.exists():
            self.skipTest('Fixture externa opcional ausente')
        d, extra = parse_investidor10(fixture.read_text(encoding='utf-8-sig'))
        self.assertGreater(d['price'], 0)
        self.assertGreater(d['eps'], 0)
        self.assertGreater(d['bvps'], 0)
        self.assertAlmostEqual(d['dps'], d['price']*d['dy']/100)

if __name__ == '__main__':
    unittest.main()
