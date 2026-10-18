"""Subconjunto do protocolo Hrana HTTP para SQLite/libSQL no Turso."""
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from hosting import ConfigurationError

class RemoteDatabaseError(RuntimeError):
    def __init__(self, code, message):
        self.code = re.sub(r'[^A-Z0-9_]', '_', str(code).upper())[:80] or 'DATABASE_ERROR'
        super().__init__(message)

def database_error(error, stage):
    error = error if isinstance(error, dict) else {}
    code = error.get('code') or 'DATABASE_ERROR'
    normalized_code = str(code).upper()
    message = str(error.get('message', '')).lower()
    if normalized_code == 'BLOCKED':
        explanation = 'O Turso bloqueou este comando por uma política do servidor. Verifique no painel Turso os limites de uso e os bloqueios de leitura/escrita da organização ou do banco. Tentar novamente sem resolver o bloqueio pode não funcionar.'
    elif any(word in message for word in ('readonly', 'read-only', 'not authorized', 'permission denied')) or normalized_code in ('SQLITE_AUTH', 'SQLITE_READONLY'):
        explanation = 'O token Turso não permite inicializar ou gravar as tabelas. Configure TURSO_AUTH_TOKEN com permissão de leitura e escrita.'
    elif 'no such table' in message:
        explanation = 'O banco remoto não encontrou uma tabela necessária. Confira se a URL aponta para o banco correto e se o token permite criar as tabelas.'
    elif normalized_code.startswith(('SQLITE_BUSY', 'SQLITE_LOCKED')) or re.search(r'\b(locked|busy)\b', message):
        explanation = 'O banco remoto está ocupado. Tente novamente em alguns instantes.'
    elif 'autoincrement' in message:
        explanation = 'O banco remoto rejeitou AUTOINCREMENT na criação do histórico. Confira a compatibilidade SQLite/libSQL do banco configurado.'
    elif any(word in message for word in ('syntax error', 'unsupported', 'not supported')):
        explanation = 'O banco remoto rejeitou a sintaxe ou um recurso SQL usado pelo aplicativo. Confira a compatibilidade SQLite/libSQL do banco.'
    else:
        explanation = 'O Turso recusou uma operação do banco. Consulte o código e a etapa nos logs da Vercel.'
    exc = RemoteDatabaseError(code, explanation)
    exc.stage = stage
    exc.schema_missing = 'no such table' in message and normalized_code != 'BLOCKED'
    # Não registrar mensagens SQL, payloads ou credenciais retornados pelo provedor.
    print(f'remote_sqlite_error code={exc.code} stage={stage}', flush=True)
    return exc

def step_slots(value, count):
    """Aceita arrays posicionais ou mapas esparsos por índice de etapa."""
    if isinstance(value, list) and len(value) == count:
        return value
    if isinstance(value, dict) and all(str(k).isdigit() and 0 <= int(k) < count for k in value):
        return [value.get(str(i), value.get(i)) for i in range(count)]
    raise RemoteDatabaseError('TURSO_RESPONSE_INVALID', 'O Turso retornou um formato inesperado para as etapas da consulta.')

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
    columns = [col['name'] for col in result.get('cols') or []]
    def decode(cell):
        kind, value = cell['type'], cell.get('value')
        return None if kind == 'null' else int(value) if kind == 'integer' else float(value) if kind == 'float' else value
    return [dict(zip(columns, map(decode, row))) for row in result.get('rows') or []]

def run(statements, transaction=False):
    url = os.environ.get('TURSO_DATABASE_URL', '').strip()
    token = os.environ.get('TURSO_AUTH_TOKEN', '').strip()
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
    except urllib.error.HTTPError as error:
        messages = {
            401: 'O Turso rejeitou a autenticação (HTTP 401). Confira TURSO_AUTH_TOKEN e gere um token válido para o banco configurado.',
            403: 'O Turso negou acesso (HTTP 403). Confira as permissões do token e as regras de acesso do banco.',
            404: 'O endpoint Turso não foi encontrado (HTTP 404). Use a URL do banco, sem /v2/pipeline nem caminhos adicionais.',
            429: 'O Turso atingiu um limite de requisições (HTTP 429). Tente novamente mais tarde.'
        }
        raise RemoteDatabaseError(f'TURSO_HTTP_{error.code}', messages.get(error.code, f'O Turso retornou HTTP {error.code}. Consulte os logs e a disponibilidade do serviço.')) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise RemoteDatabaseError('TURSO_RESPONSE_INVALID', 'A URL configurada não retornou JSON válido do Turso. Confira a URL do banco.') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ConfigurationError('Não foi possível conectar ao SQLite remoto. Confira URL, token e disponibilidade do Turso.') from None
    try:
        result = body['results'][0]
        if result['type'] != 'ok':
            raise database_error(result.get('error'), 'pipeline')
        if result['response']['type'] != 'batch':
            raise RemoteDatabaseError('TURSO_RESPONSE_INVALID', 'A resposta do Turso não corresponde à consulta em lote enviada.')
        batch = result['response']['result']
        results = step_slots(batch['step_results'], len(steps))
        errors = step_slots(batch['step_errors'], len(steps))
        for index, error in enumerate(errors):
            if error is not None:
                sql = steps[index]['stmt']['sql']
                operation = sql.split()[0]
                raise database_error(error, f'{index}:{operation}')
        rows = results[offset:offset+len(statements)]
        if any(row is None for row in rows):
            raise RemoteDatabaseError('TURSO_INCOMPLETE_RESULT', 'O Turso não concluiu todas as consultas. Consulte os logs da Vercel.')
        return [decode_rows(row) for row in rows]
    except (KeyError, IndexError, TypeError, ValueError):
        raise RemoteDatabaseError('TURSO_RESPONSE_INVALID', 'O Turso retornou uma resposta incompatível com o protocolo esperado.') from None
