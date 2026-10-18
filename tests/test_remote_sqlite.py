"""Exercita o adaptador HTTP com um servidor Hrana simulado e SQLite real."""
import io
import json
import os
import sqlite3
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import remote_sqlite
from hosting import ConfigurationError

class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:',isolation_level=None)
        self.operations = []
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
        self.operations.append([step['stmt']['sql'] for step in steps])
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
            except sqlite3.Error as error:
                results.append(None)
                errors.append({'code':'SQLITE_ERROR','message':str(error)})
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

    def reply(self, batch):
        return io.BytesIO(json.dumps({'results':[{'type':'ok','response':{'type':'batch','result':batch}}]}).encode())

    def test_sql_permission_error_is_actionable_and_redacted(self):
        batch={'step_results':[None], 'step_errors':[{'code':'SQLITE_AUTH','message':'not authorized SECRET_TOKEN'}]}
        with patch.object(remote_sqlite.urllib.request,'urlopen',return_value=self.reply(batch)):
            with self.assertRaises(remote_sqlite.RemoteDatabaseError) as caught:
                server.get_asset('WEGE3')
        self.assertEqual(caught.exception.code,'SQLITE_AUTH')
        self.assertEqual(caught.exception.stage,'0:SELECT')
        self.assertIn('leitura e escrita',str(caught.exception))
        self.assertNotIn('SECRET_TOKEN',str(caught.exception))

    def test_http_auth_error_is_not_generic(self):
        error=urllib.error.HTTPError('https://example.turso.io',401,'Unauthorized',{},None)
        with patch.object(remote_sqlite.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(remote_sqlite.RemoteDatabaseError) as caught:
                server.get_asset('WEGE3')
        self.assertEqual(caught.exception.code,'TURSO_HTTP_401')

    def test_malformed_reply_is_not_uncaught_python_error(self):
        for body in (b'<html>Not an API</html>',b'{}',b'{"results":[]}'):
            with patch.object(remote_sqlite.urllib.request,'urlopen',return_value=io.BytesIO(body)):
                with self.assertRaises(remote_sqlite.RemoteDatabaseError) as caught:
                    server.get_asset('WEGE3')
                self.assertEqual(caught.exception.code,'TURSO_RESPONSE_INVALID')

    def test_sparse_slots_and_nullable_empty_rows(self):
        result={'cols':None,'rows':None}
        self.assertEqual(remote_sqlite.decode_rows(result),[])
        self.assertEqual(remote_sqlite.step_slots({'0':result},2),[result,None])
        for invalid in (None,{'5':result},[result]):
            with self.assertRaises(remote_sqlite.RemoteDatabaseError):
                remote_sqlite.step_slots(invalid,2)

    def test_blocked_is_policy_error_not_busy(self):
        error=remote_sqlite.database_error({'code':'BLOCKED','message':'statement blocked'},'0:CREATE')
        self.assertIn('política',str(error))
        self.assertNotIn('ocupado',str(error))
        self.assertFalse(error.schema_missing)
        busy=remote_sqlite.database_error({'code':'SQLITE_BUSY','message':'database is locked'},'0:SELECT')
        self.assertIn('ocupado',str(busy))

    def test_existing_schema_reads_never_run_create(self):
        server.init()
        self.operations.clear()
        server.get_asset('WEGE3')
        server.get_asset('PETR4')
        self.assertEqual(len(self.operations),2)
        self.assertTrue(all(len(sqls)==1 and sqls[0].startswith('SELECT') for sqls in self.operations))

    def test_empty_database_initializes_only_after_missing_table(self):
        self.assertEqual(server.get_asset('WEGE3')['ticker'],'WEGE3')
        self.assertEqual(len(self.operations),3)
        self.assertTrue(self.operations[0][0].startswith('SELECT'))
        self.assertTrue(any(sql.startswith('CREATE') for sql in self.operations[1]))
        self.assertTrue(self.operations[2][0].startswith('SELECT'))
        self.operations.clear()
        server.get_asset('WEGE3')
        self.assertEqual(len(self.operations),1)

    def test_blocked_query_is_not_retried_or_followed_by_ddl(self):
        batch={'step_results':[None],'step_errors':[{'code':'BLOCKED','message':'blocked reads'}]}
        with patch.object(remote_sqlite.urllib.request,'urlopen',return_value=self.reply(batch)) as transport:
            with self.assertRaises(remote_sqlite.RemoteDatabaseError) as caught:
                server.get_asset('WEGE3')
        self.assertEqual(caught.exception.code,'BLOCKED')
        self.assertEqual(transport.call_count,1)

    def test_health_probe_does_not_require_tables(self):
        rows=server.run_sql([('SELECT 1 AS ok',())])
        self.assertEqual(rows[0][0]['ok'],1)
        self.assertEqual(len(self.operations),1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0],0)

if __name__ == '__main__':
    unittest.main()
