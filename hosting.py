"""Configuração de hosts e sessões para execução local e Vercel."""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit

DEPLOYED_HOST = 'analise-de-acoes-b3j85d53r-alex-chiudini.vercel.app'
LOCAL_SECRET = secrets.token_urlsafe(32)

class ConfigurationError(RuntimeError):
    pass

def is_vercel():
    return os.environ.get('VERCEL') == '1' or bool(os.environ.get('VERCEL_URL'))

def hostname(value):
    if not value or any(c.isspace() for c in value) or any(c in value for c in '@,\\?#'):
        return None
    try:
        parsed = urlsplit(value if '://' in value else '//' + value)
        if parsed.path not in ('', '/') or parsed.scheme not in ('', 'http', 'https'):
            return None
        _ = parsed.port
        return parsed.hostname.lower().rstrip('.') if parsed.hostname else None
    except ValueError:
        return None

def allowed_host(value):
    incoming = hostname(value)
    if not incoming:
        return False
    allowed = {'localhost', '127.0.0.1', DEPLOYED_HOST}
    configured = os.environ.get('ALLOWED_HOSTS', '').split(',')
    configured += [os.environ.get(k, '') for k in ('VERCEL_URL', 'VERCEL_PROJECT_PRODUCTION_URL', 'VERCEL_BRANCH_URL')]
    allowed.update(filter(None, (hostname(v.strip()) for v in configured)))
    return incoming in allowed

def session_secret():
    secret = os.environ.get('SESSION_SECRET', '')
    if is_vercel() and len(secret) < 32:
        raise ConfigurationError('Configure SESSION_SECRET na Vercel com pelo menos 32 caracteres aleatórios e faça um novo deploy.')
    return secret or LOCAL_SECRET

def session_token():
    # Token assinado com validade, aceito por instâncias diferentes da mesma implantação.
    expires = str(int(time.time()) + 86400)
    signature = hmac.new(session_secret().encode(), expires.encode(), hashlib.sha256).hexdigest()
    return expires + '.' + signature

def valid_session(token):
    if not token:
        return False
    try:
        expires, supplied = token.split('.', 1)
        if int(expires) < time.time() or int(expires) > time.time() + 86460:
            return False
        expected = hmac.new(session_secret().encode(), expires.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(supplied, expected)
    except (ValueError, AttributeError):
        return False
