"""Exercita o adaptador HTTP com um servidor Hrana simulado e SQLite real."""
import io
import json
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import remote_sqlite
from hosting import ConfigurationError

class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:',isolation_level=None)
        self.env = patch.dict(os.environ, {'VERCEL':'1','TURSO_DATABASE_URL':'libsql://example.turso.io','TURSO_AUTH_TOKEN':'test-token','SESSION_SECRET':'a'*32})
        self.env.start()
        self.transport = patch.object(remote_sqlite.urllib.request,'urlopen',side_effect=self.request)
        self.transport.start()

    def tearDown(self):
        self.transport.stop()
        self.env.stop()
        self.db.close()

    def request(self,request,timeout):
        self.assertEqual(request.full_url,'https://example.turso.io/v2/pipeline')
        self.assertEqual(request.get_header('Authorization'),'Bearer test-token')
        payload = json.loads(request.data)
        self.assertEqual(payload['requests'][-1],{'type':'close'})
        steps = payload['requests'][0]['batch']['steps']
        results, errors = [], []
        def condition(cond):
            if cond['type']=='ok':
                return results[cond['step']] is not None
            if cond['type']=='not':
                return not condition(cond['cond'])
            return all(condition(c) for c in cond['conds'])
        for step in steps:
            if step.get('condition') and not condition(step['condition']):
                results.append(None)
                errors.append(None)
                continue
            stmt=step['stmt']
            args=[None if arg['type']=='null' else int(arg['value']) if arg['type']=='integer' else arg['value'] for arg in stmt.get('args',[])]
            try:
                cursor=self.db.execute(stmt['sql'],args)
                cols=[{'name':col[0]} for col in cursor.description or []]
                rows=[[remote_sqlite.argument(v) for v in row] for row in cursor.fetchall()]
                results.append({'cols':cols,'rows':rows})
                errors.append(None)
            except sqlite3.Error:
                results.append(None)
                errors.append({'message':'test SQLite failure'})
        return io.BytesIO(json.dumps({'results':[{'type':'ok','response':{'type':'batch','result':{'step_results':results,'step_errors':errors}}},{'type':'ok','response':{'type':'close'}}]}).encode())

    def test_save_read_and_history(self):
        server.init()
        asset=server.get_asset('WEGE3')
        asset['data'].update(price=47.99,eps=1.49,bvps=4.49,dps=1.85,ipca=4.9)
        server.save_asset(asset)
        self.assertEqual(server.get_asset('WEGE3')['data']['price'],47.99)
        self.assertEqual(server.run_sql([('SELECT count(*) AS count FROM analyses',())])[0][0]['count'],1)

    def test_write_is_atomic_on_history_failure(self):
        server.init()
        self.db.execute("CREATE TRIGGER fail_history BEFORE INSERT ON analyses BEGIN SELECT RAISE(ABORT,'fail'); END")
        asset=server.get_asset('TEST3')
        asset['data']['price']=10
        with self.assertRaises(RuntimeError):
            server.save_asset(asset)
        self.assertEqual(self.db.execute('SELECT count(*) FROM assets').fetchone()[0],0)

    def test_cloud_never_uses_ephemeral_sqlite(self):
        with patch.dict(os.environ, {'TURSO_DATABASE_URL':''}):
            with self.assertRaises(ConfigurationError):
                server.get_asset('WEGE3')

if __name__ == '__main__':
    unittest.main()
