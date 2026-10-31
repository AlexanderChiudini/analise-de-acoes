import json
import math
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import calculations
from test_http import HTTPTests

INPUTS = dict(price=20, eps=2, bvps=10, dps=1.5, fcf_per_share=2,
              growth=5, terminal_growth=3, dcf_years=10, desired_yield=6,
              safety_margin=20, historical_pe=12, historical_pb=2,
              discount_rate=10, graham_factor=15)

class CalculationTests(unittest.TestCase):
    def test_formulas(self):
        r = calculations.run(INPUTS)['results']
        self.assertEqual(r['pe_history']['value'], 24)
        self.assertEqual(r['pb_history']['ceiling'], 16)
        self.assertEqual(r['bazin']['value'], 25)
        self.assertAlmostEqual(r['graham']['ceiling'], math.sqrt(300)*.8)
        expected = sum(2*1.05**t/1.1**t for t in range(1,11)) + 2*1.05**10*1.03/.07/1.1**10
        self.assertAlmostEqual(r['dcf']['value'], expected)
        self.assertAlmostEqual(r['pe_history']['potential'], -4)

    def test_invalid_and_missing(self):
        for patch in [dict(graham_factor=-1),dict(discount_rate=True),dict(historical_pb='x'),dict(safety_margin=100),dict(dcf_years=2.5)]:
            with self.assertRaises(ValueError):
                calculations.run(dict(INPUTS, **patch))
        self.assertIsNone(calculations.run(dict(INPUTS, terminal_growth=10))['results']['dcf']['value'])
        self.assertIsNone(calculations.run(dict(INPUTS, eps=-1))['results']['graham']['value'])
        self.assertIsNone(calculations.run(dict(INPUTS, fcf_per_share=None))['results']['dcf']['value'])

    def test_daily_history(self):
        rows = [{'asset': {'data': dict(price=p,eps=2,bvps=10)}, 'created_at': day} for p,day in [(30,'2026-10-30'),(20,'2026-10-30'),(10,'2026-10-29')]]
        h = calculations.historical(rows)
        self.assertEqual(h['pe']['count'],2)
        self.assertEqual(h['pe']['value'],10)
        self.assertIsNone(calculations.historical(rows[:2])['pe']['value'])

class CalculationHTTPTests(HTTPTests):
    def test_calculation_history(self):
        self.request('/api/assets/VALE3/save', {'price':20,'eps':2,'bvps':10})
        context=json.loads(self.request('/api/assets/VALE3/calculations'))
        self.assertEqual(context['inputs']['price'],20)
        self.assertEqual(context['inputs']['graham_factor'],15)
        self.request('/api/assets/VALE3/calculations/simulate',INPUTS)
        self.assertEqual(json.loads(self.request('/api/assets/VALE3/calculations'))['history'],[])
        saved=json.loads(self.request('/api/assets/VALE3/calculations/save',INPUTS))
        context=json.loads(self.request('/api/assets/VALE3/calculations'))
        self.assertEqual(context['history'][0]['results'],saved['results'])
        self.assertEqual(context['history'][0]['inputs']['graham_factor'],15)
        self.assertEqual(json.loads(self.request('/api/assets/VALE3'))['data']['price'],20)
