"""Subconjunto do protocolo Hrana HTTP para SQLite/libSQL no Turso."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from hosting import ConfigurationError

def configured():
    return bool(os.environ.get('TURSO_DATABASE_URL'))

def argument(value):
    if value is None:
        return {'type': 'null'}
    if isinstance(value, int):
        return {'type': 'integer', 'value': str(value)}
    if isinstance(value, float):
        return {'type': 'float', 'value': value}
    return {'type': 'text', 'value': str(value)}

def decode_rows(result):
    columns = [col['name'] for col in result.get('cols', [])]
    def decode(cell):
        kind, value = cell['type'], cell.get('value')
        return None if kind == 'null' else int(value) if kind == 'integer' else float(value) if kind == 'float' else value
    return [dict(zip(columns, map(decode, row))) for row in result.get('rows', [])]

def run(statements, transaction=False):
    url = os.environ.get('TURSO_DATABASE_URL', '').strip()
    token = os.environ.get('TURSO_AUTH_TOKEN', '')
    if not url or not token:
        raise ConfigurationError('Configure TURSO_DATABASE_URL e TURSO_AUTH_TOKEN para armazenar as análises na Vercel.')
    for scheme in ('libsql://', 'turso://'):
        if url.startswith(scheme):
            url = 'https://' + url[len(scheme):]
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError('TURSO_DATABASE_URL deve ser uma URL HTTPS ou libsql válida, sem credenciais na URL.')
    steps = []
    if transaction:
        steps.append({'stmt': {'sql': 'BEGIN IMMEDIATE', 'want_rows': False}})
    offset = len(steps)
    for sql, args in statements:
        step = {'stmt': {'sql': sql, 'args': [argument(v) for v in args], 'want_rows': True}}
        if steps:
            step['condition'] = {'type': 'ok', 'step': len(steps)-1}
        steps.append(step)
    if transaction:
        commit_index = len(steps)
        steps.append({'condition': {'type': 'ok', 'step': commit_index-1}, 'stmt': {'sql': 'COMMIT', 'want_rows': False}})
        steps.append({'condition': {'type': 'and', 'conds': [{'type': 'ok', 'step': 0}, {'type': 'not', 'cond': {'type': 'ok', 'step': commit_index}}]}, 'stmt': {'sql': 'ROLLBACK', 'want_rows': False}})
    payload = {'requests': [{'type': 'batch', 'batch': {'steps': steps}}, {'type': 'close'}]}
    request = urllib.request.Request(url.rstrip('/')+'/v2/pipeline', data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConfigurationError('Não foi possível conectar ao SQLite remoto. Confira URL, token e disponibilidade do Turso.') from None
    result = body['results'][0]
    if result['type'] != 'ok':
        raise RuntimeError('O SQLite remoto recusou a operação.')
    batch = result['response']['result']
    if any(batch.get('step_errors', [])):
        raise RuntimeError('Falha na operação SQLite remota; a transação foi revertida.')
    rows = batch['step_results'][offset:offset+len(statements)]
    if any(row is None for row in rows):
        raise RuntimeError('O SQLite remoto não concluiu todas as consultas.')
    return [decode_rows(row) for row in rows]
