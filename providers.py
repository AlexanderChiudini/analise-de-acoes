"""Coletores HTTP com origem por campo; não contorna autenticação ou bloqueios."""
import concurrent.futures
import html
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat()

def fetch(url, token=None):
    headers = {'User-Agent': 'EquityLab/1.0 (personal financial research)', 'Accept': 'application/json,text/html'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=18) as response:
        raw = response.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError('Resposta do provedor excedeu o limite.')
        return raw.decode('utf-8')

def number(text):
    text = html.unescape(re.sub('<[^>]+>', '', text)).strip()
    if text in ('-', '--', 'N/A', ''):
        return None
    text = re.sub(r'[^\d,\.\-]', '', text)
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None

def parse_investidor10(page):
    data, extra = {}, {}
    section = re.search(r'<section[^>]+id="cards-ticker"[^>]*>(.*?)</section>', page, re.S)
    if section:
        for cls, key in [('cotacao', 'price'), ('dy', 'dy')]:
            match = re.search(r'class="_card ' + cls + r'".*?class="_card-body".*?<span[^>]*>(.*?)</span>', section[1], re.S)
            if match and number(match[1]) is not None:
                data[key] = number(match[1])
    mapping = {'LPA': 'eps', 'VPA': 'bvps', 'ROE': 'roe', 'ROIC': 'roic', 'P/L': 'pe', 'P/VP': 'pb',
               'EV/EBITDA': 'ev_ebitda', 'DÍVIDA LÍQUIDA / EBITDA': 'net_debt_ebitda', 'MARGEM LÍQUIDA': 'net_margin'}
    for label, value in re.findall(r'data-indicator="([^"]+)"\s+data-current-value="([^"]+)"', page):
        label = html.unescape(label).upper()
        key = mapping.get(label)
        if key:
            try:
                n = float(value)
            except ValueError:
                continue
            (data if key in ('eps', 'bvps') else extra)[key] = n
    name = re.search(r'<title>(.*?)</title>', page, re.S)
    if name:
        data['company_name'] = html.unescape(name[1].split(' - Resultados')[0]).strip()
    if data.get('price') and data.get('dy') is not None:
        data['dps'] = data['price'] * data['dy'] / 100
    if not data.get('price'):
        raise ValueError('Cotação não encontrada. O layout mudou ou a coleta foi bloqueada.')
    return data, extra

def investidor10(ticker):
    url = f'https://investidor10.com.br/acoes/{ticker.lower()}/'
    data, extra = parse_investidor10(fetch(url))
    stamp = now()
    sources = {key: {'source': 'Investidor10', 'url': url, 'fetched_at': stamp,
                     'basis': 'DPS 12m estimado = cotação × DY publicado; sujeito a arredondamento' if key == 'dps' else 'Valor publicado na página; conferir período contábil na fonte'} for key in data}
    return data, extra, sources

def brapi(ticker):
    url = f'https://brapi.dev/api/quote/{ticker}'
    payload = json.loads(fetch(url, os.environ.get('BRAPI_TOKEN')))
    q = payload.get('results', [{}])[0]
    data = {key: q.get(field) for key, field in [('price', 'regularMarketPrice'), ('eps', 'earningsPerShare'), ('company_name', 'longName')] if q.get(field) is not None}
    if not data.get('price'):
        raise ValueError('Provedor não retornou cotação.')
    sources = {key: {'source': 'brapi', 'url': url, 'fetched_at': now(), 'as_of': q.get('regularMarketTime'), 'basis': 'Cotação/indicador retornado pela API'} for key in data}
    return data, {}, sources

def bcb():
    url = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.13522/dados/ultimos/1?formato=json'
    row = json.loads(fetch(url))[0]
    value = float(row['valor'])
    return {'ipca': value}, {}, {'ipca': {'source': 'BCB / SGS 13522', 'url': url, 'fetched_at': now(), 'as_of': row['data'], 'basis': 'IPCA acumulado em 12 meses (%)'}}

def inflation():
    # O SIDRA publica o mesmo indicador diretamente no IBGE e evita dependência de um só host.
    url = 'https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2265/p/last%201'
    try:
        rows = json.loads(fetch(url))
        row = next(r for r in rows if r.get('D2C') == '2265')
        if row.get('MC') != '2':
            raise ValueError('Unidade inesperada na série IPCA.')
        value = float(row['V'])
        return {'ipca': value}, {}, {'ipca': {'source': 'IBGE / SIDRA 1737', 'url': url, 'fetched_at': now(), 'as_of': row['D3N'], 'basis': 'IPCA acumulado em 12 meses (%) · variável 2265'}}
    except Exception:
        return bcb()

def collect(ticker):
    merged, extras, sources, errors = {}, {}, {}, []
    # Aguardar ambos, aplicar prioridade estável: página com indicadores, brapi como fallback.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [('Investidor10', lambda: investidor10(ticker)), ('IPCA', inflation)]
        if os.environ.get('BRAPI_TOKEN') or ticker in {'PETR4', 'MGLU3', 'VALE3', 'ITUB4'}:
            jobs.append(('brapi', lambda: brapi(ticker)))
        futures = {name: pool.submit(fn) for name, fn in jobs}
        results = {}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except Exception as e:
                errors.append(f'{name}: coleta indisponível ({type(e).__name__}).')
        for name in ('brapi', 'Investidor10', 'IPCA'):
            if name in results:
                data, ext, src = results[name]
                merged.update(data)
                extras.update(ext)
                sources.update(src)
    if not merged:
        raise ValueError('Não foi possível obter dados. ' + ' '.join(errors) + ' Você pode preencher manualmente.')
    return merged, extras, sources, errors
