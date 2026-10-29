"""Análise por regras de ações B3. Sem IA, rede ou execução de ordens."""
import math
import re
from datetime import datetime, timezone

from models import DEFAULTS, calculate

# Cada critério tem o mesmo peso. A nota mede aderência, não retorno esperado.
CRITERIA = {
    'max_pe': ('P/L positivo até', 'pe', 'max', 15.0, 'x'),
    'max_pb': ('P/VP positivo até', 'pb', 'max', 2.0, 'x'),
    'min_dy': ('Dividend yield mínimo', 'dy', 'min', 4.0, '%'),
    'min_roe': ('ROE publicado mínimo', 'roe', 'min', 10.0, '%'),
    'max_debt': ('Dívida líquida/EBITDA máxima', 'net_debt_ebitda', 'max', 3.0, 'x'),
    'min_potential': ('Potencial mínimo com margem', 'potential', 'min', 0.0, '%'),
}


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def rules_config(raw=None):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or set(raw) - CRITERIA.keys():
        raise ValueError('Critérios de análise inválidos.')
    out = {}
    for key, (_, _, _, default, _) in CRITERIA.items():
        value = raw.get(key, default)
        if value is not None and (number(value) is None or abs(value) > 100000):
            raise ValueError('Limite inválido para ' + key)
        out[key] = value
    if not any(v is not None for v in out.values()):
        raise ValueError('Ative pelo menos um critério.')
    return out


def analyze(assets, raw_rules=None):
    rules = rules_config(raw_rules)
    rows, excluded = [], []
    for asset in assets:
        ticker = asset.get('ticker', '')
        # Ações ON, PN e units; não inclui FIIs, ETFs, BDRs ou opções.
        sources = asset.get('sources', {})
        verified_unit = any(s.get('source') == 'Investidor10' and
                            s.get('url') == f'https://investidor10.com.br/acoes/{ticker.lower()}/'
                            for s in sources.values())
        if (not re.fullmatch(r'[A-Z][A-Z0-9]{3}(?:3|4|5|6|7|8|11)', ticker)
                or (ticker.endswith('11') and not verified_unit)):
            excluded.append(ticker)
            continue
        data = dict(DEFAULTS, **asset.get('data', {}))
        extra = asset.get('extra', {})
        analysis = calculate(data)
        metrics = {key: number(analysis['indicators'].get(key)) for key in ('pe', 'pb')}
        metrics.update(dy=number(data.get('dy')), roe=number(extra.get('roe')),
                       net_debt_ebitda=number(extra.get('net_debt_ebitda')),
                       potential=number(analysis['potential']['safe_average']))
        checks = []
        for key, (label, metric, direction, _, unit) in CRITERIA.items():
            limit = rules[key]
            if limit is None:
                continue
            value = metrics[metric]
            missing = value is None
            positive = metric not in ('pe', 'pb') or (value is not None and value > 0)
            passed = not missing and positive and (value <= limit if direction == 'max' else value >= limit)
            checks.append({'key': key, 'label': label, 'value': value, 'limit': limit,
                           'unit': unit, 'status': 'missing' if missing else 'pass' if passed else 'fail'})
        missing = sum(c['status'] == 'missing' for c in checks)
        passed = sum(c['status'] == 'pass' for c in checks)
        status = 'insufficient' if missing else 'passed' if passed == len(checks) else 'failed'
        sources = asset.get('sources', {})
        warnings = list(asset.get('warnings', [])) + analysis['warnings']
        for source in sources.values():
            stamp = source.get('fetched_at')
            if stamp:
                try:
                    fetched = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
                    if (datetime.now(timezone.utc) - fetched).days > 7:
                        warnings.append('Há dados coletados há mais de 7 dias. Confira as datas das fontes.')
                        break
                except (ValueError, TypeError):
                    continue
        if any(s.get('source') == 'Manual' for s in sources.values()):
            warnings.append('Inclui dados ou premissas manuais; confira as fontes.')
        rows.append({'ticker': ticker, 'name': data.get('company_name', ticker), 'status': status,
                     'score': round(100 * passed / len(checks), 1) if not missing else None,
                     'coverage': round(100 * (len(checks) - missing) / len(checks), 1),
                     'checks': checks, 'metrics': metrics, 'price': data.get('price'),
                     'safe_price': analysis['values']['safe_average'],
                     'updated_at': asset.get('updated_at'), 'sources': sources,
                     'extra': extra, 'data': data, 'warnings': warnings})
    rows.sort(key=lambda r: ({'passed': 0, 'failed': 1, 'insufficient': 2}[r['status']],
                             -(r['score'] or 0), r['ticker']))
    return {'created_at': datetime.now(timezone.utc).isoformat(), 'rules': rules, 'rows': rows,
            'excluded': excluded, 'counts': {status: sum(r['status'] == status for r in rows)
                                           for status in ('passed', 'failed', 'insufficient')}}
