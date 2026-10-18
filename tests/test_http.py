import csv
import io
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_db, cls.old_port = server.DB, server.PORT
        server.DB = Path(cls.temp.name)/'integration.sqlite3'
        server.init()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        server.PORT = cls.http.server_port
        cls.base = f'http://127.0.0.1:{server.PORT}'
        cls.thread = threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        server.DB, server.PORT = cls.old_db, cls.old_port
        cls.temp.cleanup()

    def request(self,path,body=None,authorized=True,host=None):
        headers = {'Content-Type':'application/json'}
        if host:
            headers['Host'] = host
        if authorized:
            headers['X-Session-Token'] = server.TOKEN
        req = urllib.request.Request(self.base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(req) as response:
            return response.read()

    def test_full_lifecycle_and_manual_override(self):
        payload = {'price':47.99,'dy':3.85,'dps':1.85,'eps':1.49,'bvps':4.49,'growth':5,'ipca':4.9,'category':'Growth'}
        saved = json.loads(self.request('/api/assets/WEGE3/save',payload))
        self.assertEqual(saved['analysis']['final_signal'],'CARA')
        self.assertEqual(saved['sources']['price']['source'],'Manual')
        automatic = ({'price':48,'ipca':4.58},{},{k:{'source':'Test','basis':'Fixture'} for k in ('price','ipca')},[])
        with patch.object(server,'collect',return_value=automatic):
            refreshed = json.loads(self.request('/api/assets/WEGE3/refresh',{}))
            self.assertEqual(refreshed['data']['price'],47.99)
            restored = json.loads(self.request('/api/assets/WEGE3/refresh',{'automatic_fields':['price']}))
            self.assertEqual(restored['data']['price'],48)
            self.assertEqual(restored['sources']['price']['source'],'Test')
        history = json.loads(self.request('/api/assets/WEGE3/history'))
        self.assertEqual(len(history),3)
        self.assertEqual(history[-1]['asset']['data']['price'],47.99)
        exported = self.request('/api/assets/WEGE3/export').decode('utf-8-sig')
        rows = list(csv.reader(io.StringIO(exported),delimiter=';'))
        self.assertEqual(len(rows[0]),21)
        self.assertEqual(len(rows[1]),21)
        self.assertEqual(rows[1][0],'WEGE3')
        before = len(history)
        self.request('/api/assets/WEGE3/simulate',{'price':30})
        self.assertEqual(len(json.loads(self.request('/api/assets/WEGE3/history'))),before)

    def test_session_and_validation(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/assets/TEST3/save',{'price':10},authorized=False)
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/assets/TEST3/save',{'price':0})
        self.assertEqual(error.exception.code,400)

    def test_hosted_host_serves_page_and_post(self):
        host = 'analise-de-acoes-b3j85d53r-alex-chiudini.vercel.app'
        self.assertIn(b'equitylab',self.request('/',host=host))
        result = json.loads(self.request('/api/assets/TEST3/simulate',{'price':10},host=host))
        self.assertIn('analysis',result)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/',host='untrusted.vercel.app')
        self.assertEqual(error.exception.code,403)

    def test_vercel_rewritten_paths(self):
        def rewritten(path):
            return '/api/index?__route='+quote(path,safe='')
        self.assertIn(b'equitylab',self.request(rewritten('/')))
        self.assertIn(b'equitylab',self.request('/api/index'))
        self.assertIn(b'const qualityItems',self.request(rewritten('/app.js')))
        self.assertIn(b':root',self.request(rewritten('/style.css')))
        session=json.loads(self.request(rewritten('/api/session')))
        self.assertIn('token',session)
        self.assertEqual(json.loads(self.request(rewritten('/api/health')))['status'],'ok')
        self.assertIsInstance(json.loads(self.request(rewritten('/api/assets'))),list)
        result=json.loads(self.request(rewritten('/api/assets/TEST3/simulate'),{'price':10}))
        self.assertIn('analysis',result)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(rewritten('/unknown-route'))
        self.assertEqual(error.exception.code,404)

    def test_rewritten_path_validation(self):
        for path in ('/api/index?__route=//evil.com', '/api/index?__route=/&__route=/api/session', '/api/index?__route=relative'):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path)
            self.assertEqual(error.exception.code,400)

    def test_database_error_response_preserves_safe_diagnostic(self):
        error=server.remote_sqlite.database_error({'code':'SQLITE_AUTH','message':'not authorized secret-value'},'0:CREATE')
        with patch.object(server,'get_asset',side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/assets/WEGE3')
            self.assertEqual(caught.exception.code,502)
            body=json.loads(caught.exception.read())
            self.assertEqual(body['code'],'SQLITE_AUTH')
            self.assertEqual(body['stage'],'0:CREATE')
            self.assertNotIn('secret-value',json.dumps(body))

if __name__ == '__main__':
    unittest.main()
