"""Descoberta de ações B3 a partir de catálogos públicos e coleta por ticker."""
import json
import os
import re
import urllib.error
import urllib.request
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from models import DEFAULTS, FIELDS, validate
from providers import fetch, investidor10, number, inflation
from automatic import analyze, rules_config

STOCK = re.compile(r'[A-Z][A-Z0-9]{3}(?:[3-8]|11)')
CATALOG_URL = 'https://www.fundamentus.com.br/resultado.php'
BRAPI_CATALOG_URL = 'https://brapi.dev/api/quote/list?type=stock&sortBy=volume&sortOrder=desc&limit=100&page='
ASSUMPTIONS = {'growth', 'desired_yield', 'real_return', 'safety_margin'}


class SourceUnavailable(ValueError):
    pass


def parse_catalog(page):
    # Apenas a tabela de resultados; não inclui tickers citados na navegação.
    body = re.search(r'<tbody\b[^>]*>(.*?)</tbody>', page, re.S | re.I)
    if not body:
        raise ValueError('A fonte não retornou a tabela de ações.')
    tickers = set()
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', body[1], re.S | re.I):
        match = re.search(r'detalhes\.php\?papel=([A-Za-z0-9]+)', row)
        cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)
        if not match or len(cells) < 2:
            continue
        ticker = match[1].upper()
        if STOCK.fullmatch(ticker) and (number(cells[1]) or 0) > 0 and (len(cells) <= 17 or (number(cells[17]) or 0) > 0):
            tickers.add(ticker)
    if not tickers:
        raise ValueError('A lista de ações da fonte está vazia ou mudou de formato.')
    return sorted(tickers)


def universe():
    try:
        return brapi_universe()
    except (ValueError, OSError):
        pass
    try:
        req = urllib.request.Request(CATALOG_URL, headers={'User-Agent': 'EquityLab/1.0 (personal financial research)'})
        with urllib.request.urlopen(req, timeout=18) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError('Catálogo excedeu o limite de tamanho.')
        return {'tickers': parse_catalog(raw.decode('latin-1')), 'source': 'Fundamentus',
                'url': CATALOG_URL, 'fetched_at': datetime.now(timezone.utc).isoformat()}
    except (ValueError, OSError):
        raise SourceUnavailable('Não foi possível obter o catálogo público de ações B3. Tente novamente mais tarde.') from None


def brapi_universe():
    tickers, previous_symbols = [], set()
    for page in range(1, 21):
        payload = json.loads(fetch(BRAPI_CATALOG_URL + str(page), os.environ.get('BRAPI_TOKEN')))
        stocks = payload.get('stocks') if isinstance(payload, dict) else None
        if not isinstance(stocks, list) or any(not isinstance(stock, dict) for stock in stocks):
            raise SourceUnavailable('O catálogo B3 está indisponível. Tente novamente mais tarde.')
        symbols = {str(stock.get('stock', '')).upper() for stock in stocks}
        if page > 1 and symbols and symbols == previous_symbols:
            raise SourceUnavailable('A fonte repetiu a página do catálogo; busca interrompida para evitar uma lista incompleta.')
        previous_symbols = symbols
        for stock in stocks:
            ticker = str(stock.get('stock', '')).upper()
            price, volume = stock.get('close'), stock.get('volume')
            if (stock.get('type') == 'stock' and stock.get('subType', 'stock') in ('stock', 'unit')
                    and STOCK.fullmatch(ticker) and isinstance(price, (int, float)) and price > 0
                    and isinstance(volume, (int, float)) and volume > 0 and ticker not in tickers):
                tickers.append(ticker)
        more = payload.get('hasNextPage')
        if more is False or not stocks or (more is None and len(stocks) < 100):
            if not tickers:
                raise SourceUnavailable('Nenhuma ação B3 foi retornada pelo catálogo.')
            return {'tickers': tickers, 'source': 'brapi', 'url': BRAPI_CATALOG_URL + '1',
                    'fetched_at': datetime.now(timezone.utc).isoformat()}
    raise SourceUnavailable('O catálogo ultrapassou o limite de paginação. Nenhuma lista parcial foi usada.')


def assumptions_config(raw=None):
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - ASSUMPTIONS:
        raise ValueError('Premissas da descoberta inválidas.')
    values = validate(raw)
    if any(value is None for value in values.values()):
        raise ValueError('Preencha todas as premissas da descoberta.')
    return {key: values.get(key, DEFAULTS[key]) for key in ASSUMPTIONS}


def collect_candidate(ticker):
    try:
        data, extra, sources = investidor10(ticker)
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise SourceUnavailable('A fonte limitou ou bloqueou a coleta. A busca foi pausada; aguarde antes de continuar.') from None
        raise ValueError('Indicadores indisponíveis para este ticker.') from None
    validate({key: value for key, value in data.items() if key in FIELDS})
    stamp = datetime.now(timezone.utc).isoformat()
    return {'ticker': ticker, 'data': data, 'extra': extra, 'sources': sources,
            'warnings': [], 'updated_at': stamp}


def candidate_with_assumptions(asset, config):
    # Coletas isoladas dos cadastros e premissas manuais do usuário.
    return dict(asset, data={**DEFAULTS, **asset['data'], **config['assumptions'],
                                  **config.get('macro', {})},
                sources={**asset.get('sources', {}), **config.get('macro_sources', {})})


SCHEMA = [
    ('CREATE TABLE IF NOT EXISTS discovery_jobs(id TEXT PRIMARY KEY, config TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)', ()),
    ('CREATE TABLE IF NOT EXISTS discovery_items(job_id TEXT NOT NULL, ticker TEXT NOT NULL, position INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT, error TEXT, PRIMARY KEY(job_id,ticker))', ()),
    ('CREATE TABLE IF NOT EXISTS discovery_cache(ticker TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL)', ())
]


class DiscoveryService:
    def __init__(self, sql):
        self.sql = sql

    def job(self, job_id):
        rows = self.sql([('SELECT * FROM discovery_jobs WHERE id=?', (job_id,))])[0]
        if not rows:
            raise ValueError('Busca não encontrada.')
        return rows[0], json.loads(rows[0]['config'])

    def progress(self, job_id):
        job, config = self.job(job_id)
        rows = self.sql([('SELECT status,count(*) AS n FROM discovery_items WHERE job_id=? GROUP BY status', (job_id,))])[0]
        counts = {row['status']: row['n'] for row in rows}
        return {'id': job_id, 'status': job['status'], 'total': sum(counts.values()),
                'processed': counts.get('done', 0) + counts.get('error', 0),
                'failed': counts.get('error', 0), 'remaining': counts.get('pending', 0),
                'catalog': config['catalog'], 'warnings': config.get('warnings', [])}

    def latest(self):
        rows = self.sql([('SELECT id FROM discovery_jobs ORDER BY created_at DESC LIMIT 1', ())])[0]
        return self.progress(rows[0]['id']) if rows else None

    def start(self, body):
        if not isinstance(body, dict) or set(body) - {'rules', 'assumptions', 'use_cache'}:
            raise ValueError('Configuração de busca inválida.')
        rules = rules_config(body.get('rules'))
        assumptions = assumptions_config(body.get('assumptions'))
        use_cache = body.get('use_cache', True)
        if not isinstance(use_cache, bool):
            raise ValueError('Opção de cache inválida.')
        warnings, macro, macro_sources = [], {}, {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            catalog_future = pool.submit(universe)
            macro_future = pool.submit(inflation) if rules.get('min_potential') is not None else None
            catalog = catalog_future.result()
            if macro_future:
                try:
                    macro, _, macro_sources = macro_future.result()
                except (OSError, ValueError, KeyError, StopIteration):
                    warnings.append('IPCA indisponível. O critério de potencial ficará sem dados nesta busca.')
        tickers = list(dict.fromkeys(catalog['tickers']))
        if not tickers or len(tickers) > 2000 or any(not STOCK.fullmatch(ticker) for ticker in tickers):
            raise ValueError('O catálogo de ações está vazio ou inválido.')
        config = {'rules': rules, 'assumptions': assumptions, 'use_cache': use_cache,
                  'macro': macro, 'macro_sources': macro_sources, 'warnings': warnings,
                  'catalog': {key: value for key, value in catalog.items() if key != 'tickers'}}
        job_id, stamp = secrets.token_hex(16), datetime.now(timezone.utc).isoformat()
        statements = [('INSERT INTO discovery_jobs VALUES(?,?,?,?)', (job_id, json.dumps(config, ensure_ascii=False), 'running', stamp))]
        # Lotes limitados para manter compatibilidade com o limite de parâmetros SQL.
        for offset in range(0, len(tickers), 100):
            batch = tickers[offset:offset+100]
            placeholders = ','.join('(?,?,?,?)' for _ in batch)
            args = tuple(value for i, ticker in enumerate(batch, offset) for value in (job_id, ticker, i, 'pending'))
            statements.append(('INSERT INTO discovery_items(job_id,ticker,position,status) VALUES'+placeholders, args))
        self.sql(statements, transaction=True)
        return self.progress(job_id)

    def step(self, job_id):
        job, config = self.job(job_id)
        pending = self.sql([('SELECT ticker FROM discovery_items WHERE job_id=? AND status=? ORDER BY position LIMIT 1', (job_id, 'pending'))])[0]
        if not pending:
            return self.progress(job_id)
        ticker = pending[0]['ticker']
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        cached = self.sql([('SELECT payload FROM discovery_cache WHERE ticker=? AND fetched_at>=?', (ticker, cutoff))])[0] if config['use_cache'] else []
        try:
            candidate = json.loads(cached[0]['payload']) if cached else collect_candidate(ticker)
        except SourceUnavailable:
            raise
        except (ValueError, OSError, KeyError, TimeoutError) as error:
            # A falha de uma empresa não elimina as demais oportunidades.
            message = 'Não foi possível coletar os indicadores deste ticker (' + type(error).__name__ + ').'
            self.sql([('UPDATE discovery_items SET status=?,error=? WHERE job_id=? AND ticker=? AND status=?', ('error', message, job_id, ticker, 'pending'))], transaction=True)
        else:
            payload = json.dumps(candidate, ensure_ascii=False, allow_nan=False)
            statements = [('UPDATE discovery_items SET status=?,payload=?,error=NULL WHERE job_id=? AND ticker=? AND status=?', ('done', payload, job_id, ticker, 'pending'))]
            if not cached:
                statements.append(('INSERT INTO discovery_cache VALUES(?,?,?) ON CONFLICT(ticker) DO UPDATE SET payload=excluded.payload,fetched_at=excluded.fetched_at', (ticker, payload, datetime.now(timezone.utc).isoformat())))
            self.sql(statements, transaction=True)
        return dict(self.progress(job_id), ticker=ticker, cached=bool(cached))

    def result(self, job_id):
        job, config = self.job(job_id)
        items = self.sql([('SELECT ticker,status,payload,error FROM discovery_items WHERE job_id=? ORDER BY position', (job_id,))])[0]
        candidates = [candidate_with_assumptions(json.loads(item['payload']), config) for item in items if item['status'] == 'done']
        result = analyze(candidates, config['rules'])
        saved = {row['ticker'] for row in self.sql([('SELECT ticker FROM assets', ())])[0]}
        for row in result['rows']:
            row['is_new'] = row['ticker'] not in saved
        result['discovery'] = self.progress(job_id)
        result['discovery']['assumptions'] = config['assumptions']
        result['discovery']['failures'] = [{'ticker': item['ticker'], 'error': item['error']} for item in items if item['status'] == 'error']
        return result

    def finish(self, job_id):
        result = self.result(job_id)
        if result['discovery']['remaining']:
            raise ValueError('A busca ainda possui ações pendentes. Continue para concluir.')
        result['discovery']['status'] = 'completed'
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False)
        # Salvar uma única execução mesmo se a requisição final for repetida.
        self.sql([
            ('INSERT INTO automatic_runs(payload,created_at) SELECT ?,? WHERE (SELECT status FROM discovery_jobs WHERE id=?)<>?', (payload, result['created_at'], job_id, 'completed')),
            ('UPDATE discovery_jobs SET status=? WHERE id=?', ('completed', job_id))
        ], transaction=True)
        return result

    def candidate(self, job_id, ticker):
        job, config = self.job(job_id)
        rows = self.sql([('SELECT payload FROM discovery_items WHERE job_id=? AND ticker=? AND status=?', (job_id, ticker, 'done'))])[0]
        if not rows:
            raise ValueError('Esta ação ainda não foi coletada nesta busca.')
        return candidate_with_assumptions(json.loads(rows[0]['payload']), config)
