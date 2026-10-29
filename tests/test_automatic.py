import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automatic import analyze, rules_config
from models import DEFAULTS


def stock(ticker='TEST3', **changes):
    return {'ticker': ticker, 'data': dict(DEFAULTS, price=10, eps=2, bvps=12,
            dy=8, dps=1, ipca=4, **changes),
            'extra': {'roe': 15, 'net_debt_ebitda': 2}, 'sources': {}, 'warnings': []}


class AutomaticTests(unittest.TestCase):
    def test_complete_pass_and_missing_are_not_ranked_together(self):
        good = stock('ABCD3')
        missing = stock('EFGH4')
        missing['extra'].pop('roe')
        result = analyze([missing, good])
        self.assertEqual(result['counts'], {'passed': 1, 'failed': 0, 'insufficient': 1})
        self.assertEqual(result['rows'][0]['ticker'], 'ABCD3')
        self.assertEqual(result['rows'][0]['score'], 100)
        self.assertIsNone(result['rows'][1]['score'])

    def test_losses_and_negative_equity_do_not_look_cheap(self):
        company = stock()
        company['data'].update(eps=-2, bvps=-5)
        result = analyze([company], {'min_potential': None})['rows'][0]
        self.assertEqual(result['status'], 'failed')
        checks = {c['key']: c['status'] for c in result['checks']}
        self.assertEqual(checks['max_pe'], 'fail')
        self.assertEqual(checks['max_pb'], 'fail')

    def test_rules_validation_and_disabling(self):
        for bad in ([], {'unknown': 1}, {'max_pe': True}, {'max_pe': float('nan')},
                    dict.fromkeys(rules_config(), None)):
            with self.assertRaises(ValueError):
                rules_config(bad)
        result = analyze([stock()], {'max_pe': 1, 'min_dy': None})['rows'][0]
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('min_dy', [c['key'] for c in result['checks']])

    def test_b3_units_need_stock_source_and_foreign_assets_are_excluded(self):
        unit = stock('TAEE11')
        self.assertEqual(analyze([unit])['excluded'], ['TAEE11'])
        unit['sources']['price'] = {'source': 'Investidor10', 'url': 'https://investidor10.com.br/acoes/taee11/'}
        result = analyze([unit, stock('AAPL'), stock('AAPL34'), stock('HGLG11'), stock('BOVA11')])
        self.assertEqual([r['ticker'] for r in result['rows']], ['TAEE11'])
        self.assertEqual(len(result['excluded']), 4)

    def test_preserves_evidence_without_mutating_inputs(self):
        company = stock()
        company['sources']['price'] = {'source': 'Manual', 'fetched_at': '2020-01-01T00:00:00+00:00'}
        before = copy.deepcopy(company)
        row = analyze([company])['rows'][0]
        self.assertEqual(company, before)
        self.assertEqual(row['data'], company['data'])
        self.assertEqual(row['sources'], company['sources'])
        self.assertTrue(any('7 dias' in warning for warning in row['warnings']))
        self.assertTrue(any('manuais' in warning for warning in row['warnings']))


if __name__ == '__main__':
    unittest.main()
