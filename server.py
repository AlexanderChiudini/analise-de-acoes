import csv
import io
import json
import mimetypes
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import DEFAULTS, FIELDS, validate, calculate
from providers import collect
from hosting import ConfigurationError, allowed_host, is_vercel, session_token, valid_session
import remote_sqlite

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('EQUITY_DB', str(ROOT / 'data' / 'equity.sqlite3')))
TOKEN = session_token() if not is_vercel() else None
PORT = int(os.environ.get('PORT', '8765'))
SCHEMA = [
    ('CREATE TABLE IF NOT EXISTS assets(ticker TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)', ()),
    ('CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)', ()),
    ('CREATE INDEX IF NOT EXISTS idx_analyses_ticker ON analyses(ticker, id DESC)', ())
]

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect():
    if is_vercel():
        raise ConfigurationError('SQLite em arquivo local não é persistente na Vercel. Configure TURSO_DATABASE_URL e TURSO_AUTH_TOKEN.')
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=15, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    return db

def init():
    run_sql(SCHEMA, transaction=True, ensure_schema=False)

def run_sql(statements, transaction=False, ensure_schema=True):
    if remote_sqlite.configured():
        # Consultas normais não executam DDL nem exigem criação de tabelas a cada chamada.
        try:
            return remote_sqlite.run(statements, transaction=transaction)
        except remote_sqlite.RemoteDatabaseError as error:
            if not ensure_schema or not getattr(error, 'schema_missing', False):
                raise
            # A primeira operação em um banco vazio inicializa o schema uma vez.
            # Erros BLOCKED, de autenticação e de conexão nunca disparam esse caminho.
            remote_sqlite.run(SCHEMA, transaction=True)
            return remote_sqlite.run(statements, transaction=transaction)
    with connect() as db:
        if transaction:
            db.execute('BEGIN IMMEDIATE')
        return [[dict(row) for row in db.execute(sql, args).fetchall()] for sql, args in statements]

def ticker_value(value):
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z]{4}[0-9]{1,2}', value):
        raise ValueError('Ticker inválido. Exemplo: WEGE3 ou TAEE11.')
    return value

def request_path(raw_path):
    parsed = urlparse(raw_path)
    if parsed.path in ('/api/index', '/api/index.py', '/api'):
        # Rewrites podem substituir self.path pelo destino da função.
        # O caminho público é transportado explicitamente pela configuração Vercel.
        routes = parse_qs(parsed.query, keep_blank_values=True).get('__route', ['/'])
        if len(routes) != 1:
            raise ValueError('Caminho de requisição ambíguo.')
        route = routes[0]
        if not route.startswith('/') or route.startswith('//') or any(c in route for c in ('?', '#', '\\', '\x00', '\r', '\n')):
            raise ValueError('Caminho de requisição inválido.')
        return route
    return parsed.path

def get_asset(ticker):
    rows = run_sql([('SELECT payload FROM assets WHERE ticker=?', (ticker,))])[0]
    row = rows[0] if rows else None
    return json.loads(row['payload']) if row else {'ticker': ticker, 'data': dict(DEFAULTS), 'sources': {}, 'extra': {}, 'warnings': []}

def save_asset(asset):
    asset['updated_at'] = datetime.now(timezone.utc).isoformat()
    asset['analysis'] = calculate(asset['data'])
    payload = json.dumps(asset, ensure_ascii=False, allow_nan=False)
    run_sql([
        ('INSERT INTO assets VALUES(?,?,?) ON CONFLICT(ticker) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at', (asset['ticker'], payload, asset['updated_at'])),
        ('INSERT INTO analyses(ticker,payload,created_at) VALUES(?,?,?)', (asset['ticker'], payload, asset['updated_at']))
    ], transaction=True)
    return asset

class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not allowed_host(self.headers.get('Host')):
            return self.send(403, {'error': 'Host inválido. Configure este domínio em ALLOWED_HOSTS.'})
        try:
            self.route_get()
        except ConfigurationError as e:
            self.send(503, {'error': str(e)})
        except remote_sqlite.RemoteDatabaseError as e:
            self.send(502, {'error': str(e), 'code': e.code, 'stage': getattr(e, 'stage', None)})
        except ValueError as e:
            self.send(400, {'error': str(e)})
        except Exception:
            self.internal_error()

    def internal_error(self):
        import secrets
        import traceback
        error_id = secrets.token_hex(6)
        print(f'internal_error error_id={error_id}', flush=True)
        traceback.print_exc()
        self.send(500, {'error': 'Falha interna. Consulte os logs da Vercel (ou o terminal local) com o identificador informado.', 'code': 'INTERNAL_ERROR', 'error_id': error_id})

    def route_get(self):
        path = request_path(self.path)
        if path == '/api/session':
            return self.send(200, {'token': session_token(), 'storage': 'turso' if remote_sqlite.configured() else 'local'})
        if path == '/api/assets':
            rows = run_sql([('SELECT payload FROM assets ORDER BY updated_at DESC', ())])[0]
            return self.send(200, [json.loads(r['payload']) for r in rows])
        match = re.fullmatch(r'/api/assets/([^/]+)(/history|/export)?', path)
        if match:
            ticker = ticker_value(match[1])
            if match[2] == '/history':
                rows = run_sql([('SELECT id,created_at,payload FROM analyses WHERE ticker=? ORDER BY id DESC LIMIT 100', (ticker,))])[0]
                return self.send(200, [{'id': r['id'], 'created_at': r['created_at'], 'asset': json.loads(r['payload'])} for r in rows])
            asset = get_asset(ticker)
            asset['analysis'] = calculate(asset['data'])
            if match[2] == '/export':
                buf = io.StringIO()
                writer = csv.writer(buf, delimiter=';')
                a, d = asset['analysis'], asset['data']
                keys = [('Ticker', ticker), ('Categoria', d.get('category')), ('Preço Atual', d.get('price')), ('DY', d.get('dy')), ('DPS', d.get('dps')), ('LPA', d.get('eps')), ('VPA', d.get('bvps')), ('Crescimento', d.get('growth')), ('IPCA', d.get('ipca')), ('Yield Desejado', d.get('desired_yield'))]
                keys += [(label, a['values'][key]) for label, key in [('Preço Teto de Bazin', 'bazin'), ('Preço Justo de Benjamin Graham', 'graham'), ('Gordon (Meta: IPCA + 9%)', 'gordon'), ('Menor Preço Teto (O mais conservador)', 'conservative')]]
                keys += [('Potencial de Alta / Desconto (%)', a['potential']['conservative']), ('Sinal', a['signal']), ('Média', a['values']['average']), ('Margem de Segurança', d.get('safety_margin')), ('Média com margem', a['values']['safe_average']), ('Potencial com Margem (%)', a['potential']['safe_average']), ('Sinal Definitivo', a['final_signal'])]
                writer.writerow([x[0] for x in keys])
                def cell(v):
                    if isinstance(v, (int, float)):
                        return str(round(v, 6)).replace('.', ',')
                    s = str(v) if v is not None else ''
                    return "'" + s if s.startswith(('=', '+', '-', '@')) else s
                writer.writerow([cell(x[1]) for x in keys])
                return self.send(200, ('\ufeff' + buf.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8')
            return self.send(200, asset)
        if path == '/api/health':
            run_sql([('SELECT 1', ())])
            return self.send(200, {'status': 'ok', 'database': 'sqlite', 'storage': 'turso' if remote_sqlite.configured() else 'local'})
        filename = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}.get(path)
        if filename:
            file = ROOT / 'static' / filename
            content = mimetypes.guess_type(filename)[0] or 'text/plain'
            return self.send(200, file.read_bytes(), content + '; charset=utf-8')
        self.send(404, {'error': 'Rota não encontrada.'})

    def do_POST(self):
        if not allowed_host(self.headers.get('Host')):
            return self.send(403, {'error': 'Host inválido.'})
        try:
            if not valid_session(self.headers.get('X-Session-Token')):
                return self.send(403, {'error': 'Sessão inválida. Recarregue a página.'})
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 100000:
                return self.send(413, {'error': 'Conteúdo excedeu o limite.'})
            body = json.loads(self.rfile.read(size) or '{}')
            match = re.fullmatch(r'/api/assets/([^/]+)/(save|refresh|simulate)', request_path(self.path))
            if not match:
                return self.send(404, {'error': 'Rota não encontrada.'})
            ticker, action = ticker_value(match[1]), match[2]
            asset = get_asset(ticker)
            if action == 'refresh':
                automatic = body.get('automatic_fields', [])
                allowed_auto = {'price', 'dy', 'dps', 'eps', 'bvps', 'ipca'}
                if not isinstance(automatic, list) or any(key not in allowed_auto for key in automatic):
                    raise ValueError('Seleção de campos automáticos inválida.')
                data, extras, sources, warnings = collect(ticker)
                validate({key: value for key, value in data.items() if key in FIELDS})
                if any(key not in data for key in automatic):
                    raise ValueError('A fonte não retornou esse campo. Seu dado manual foi preservado.')
                for key, value in data.items():
                    if asset['sources'].get(key, {}).get('source') == 'Manual' and key not in automatic:
                        continue
                    asset['data'][key] = value
                    asset['sources'][key] = sources[key]
                asset['extra'].update(extras)
                asset['warnings'] = warnings
            else:
                updates = validate(body)
                asset['data'].update(updates)
                if action == 'simulate':
                    return self.send(200, {'analysis': calculate(asset['data'])})
                for key in updates:
                    asset['sources'][key] = {'source': 'Manual', 'fetched_at': datetime.now(timezone.utc).isoformat(), 'basis': 'Informado pelo usuário'}
            self.send(200, save_asset(asset))
        except ConfigurationError as e:
            self.send(503, {'error': str(e)})
        except remote_sqlite.RemoteDatabaseError as e:
            self.send(502, {'error': str(e), 'code': e.code, 'stage': getattr(e, 'stage', None)})
        except (ValueError, TypeError, KeyError) as e:
            self.send(400, {'error': str(e)})
        except Exception:
            self.internal_error()

if __name__ == '__main__':
    init()
    print(f'Equity Lab disponível em http://127.0.0.1:{PORT}', flush=True)
    print(f'SQLite: {DB}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
