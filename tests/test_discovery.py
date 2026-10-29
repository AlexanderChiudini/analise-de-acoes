import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import discovery


def candidate(ticker):
    return {'ticker': ticker, 'data': {'price': 10, 'eps': 2, 'bvps': 12, 'dy': 8, 'dps': 1},
            'extra': {'roe': 15, 'net_debt_ebitda': 2}, 'warnings': [],
            'sources': {'price': {'source': 'Investidor10', 'url': f'https://investidor10.com.br/acoes/{ticker.lower()}/'}},
            'updated_at': '2026-10-28T12:00:00+00:00'}


def catalog():
    return {'tickers': ['NEWC3', 'B3SA3'], 'source': 'Fixture', 'url': 'https://example.com/acoes', 'fetched_at': '2026-10-28T12:00:00+00:00'}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = server.DB
        server.DB = Path(self.temp.name)/'discovery.sqlite3'
        server.init()
        self.service = discovery.DiscoveryService(server.run_sql)
        self.patches = [patch.object(discovery, 'universe', side_effect=catalog),
                        patch.object(discovery, 'inflation', return_value=({'ipca': 4}, {}, {}))]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        server.DB = self.old_db
        self.temp.cleanup()

    def finish_steps(self, job_id):
        while self.service.progress(job_id)['remaining']:
            self.service.step(job_id)
        return self.service.finish(job_id)

    def test_discovers_without_saved_assets_and_keeps_history_separate(self):
        job = self.service.start({})
        self.assertEqual(job['total'], 2)
        with patch.object(discovery, 'collect_candidate', side_effect=candidate):
            partial = self.service.step(job['id'])
            self.assertEqual(partial['remaining'], 1)
            # Recreate service as if another serverless invocation resumed the work.
            self.service = discovery.DiscoveryService(server.run_sql)
            result = self.finish_steps(job['id'])
        self.assertEqual(result['counts']['passed'], 2)
        self.assertTrue(all(row['is_new'] for row in result['rows']))
        self.assertEqual(server.ticker_value('B3SA3'), 'B3SA3')
        self.assertEqual(server.run_sql([('SELECT count(*) AS n FROM assets', ())])[0][0]['n'], 0)
        self.service.finish(job['id'])
        self.assertEqual(server.run_sql([('SELECT count(*) AS n FROM automatic_runs', ())])[0][0]['n'], 1)

    def test_common_assumptions_and_cache_do_not_use_manual_analyses(self):
        asset = server.get_asset('NEWC3')
        asset['data'].update(price=99, growth=30)
        server.save_asset(asset)
        first = self.service.start({'assumptions': {'growth': 2}})
        with patch.object(discovery, 'collect_candidate', side_effect=candidate):
            self.finish_steps(first['id'])
        second = self.service.start({'assumptions': {'growth': 6}})
        with patch.object(discovery, 'collect_candidate') as collector:
            result = self.finish_steps(second['id'])
            collector.assert_not_called()
        row = next(row for row in result['rows'] if row['ticker'] == 'NEWC3')
        self.assertEqual(row['price'], 10)
        self.assertEqual(row['data']['growth'], 6)
        self.assertFalse(row['is_new'])
        self.assertEqual(server.get_asset('NEWC3')['data']['price'], 99)

    def test_failure_is_reported_without_approving_missing_data(self):
        job = self.service.start({})
        def collect(ticker):
            if ticker == 'NEWC3':
                raise ValueError('no data')
            asset = candidate(ticker)
            asset['extra'].pop('roe')
            return asset
        with patch.object(discovery, 'collect_candidate', side_effect=collect):
            result = self.finish_steps(job['id'])
        self.assertEqual(result['discovery']['failed'], 1)
        self.assertEqual(result['counts']['passed'], 0)
        self.assertEqual(result['counts']['insufficient'], 1)

    def test_blocked_source_preserves_pending_ticker(self):
        job = self.service.start({})
        with patch.object(discovery, 'collect_candidate', side_effect=discovery.SourceUnavailable('blocked')):
            with self.assertRaises(discovery.SourceUnavailable):
                self.service.step(job['id'])
        self.assertEqual(self.service.progress(job['id'])['remaining'], 2)
        with self.assertRaises(ValueError):
            self.service.finish(job['id'])

    def test_validation_before_network(self):
        for body in ([], {'assumptions': {'growth': 100}}, {'use_cache': 'yes'}, {'unknown': 1}):
            with patch.object(discovery, 'universe') as source:
                with self.assertRaises(ValueError):
                    self.service.start(body)
                source.assert_not_called()

    def test_brapi_pagination_and_asset_types(self):
        def stock(ticker, **changes):
            return dict(stock=ticker, type='stock', subType='stock', close=10, volume=100, **changes)
        pages = [
            {'stocks': [stock('B3SA3'), {'stock': 'BOVA11', 'type': 'fund', 'close': 10, 'volume': 100}, stock('AAPL34')], 'hasNextPage': True},
            {'stocks': [stock('NEWC3'), dict(stock('TAEE11'), subType='unit')], 'hasNextPage': False}]
        with patch.object(discovery, 'fetch', side_effect=[json.dumps(page) for page in pages]):
            result = discovery.brapi_universe()
        self.assertEqual(result['tickers'], ['B3SA3', 'NEWC3', 'TAEE11'])

    def test_fundamentus_only_parses_positive_quotes_in_table(self):
        page = '<a href="detalhes.php?papel=FAKE3">outside</a><tbody><tr><td><a href="detalhes.php?papel=B3SA3">B3SA3</a></td><td>10,50</td></tr><tr><td><a href="detalhes.php?papel=DEAD3">DEAD3</a></td><td>0,00</td></tr></tbody>'
        self.assertEqual(discovery.parse_catalog(page), ['B3SA3'])


if __name__ == '__main__':
    unittest.main()
