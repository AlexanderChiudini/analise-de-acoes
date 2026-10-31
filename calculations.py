"""Cenários independentes de valuation, com entradas e resultados auditáveis."""
import math
from statistics import mean
from models import DEFAULTS, validate, calculate

LABELS = {'pe_history': 'P/L histórico', 'pb_history': 'P/VP histórico',
          'bazin': 'Bazin personalizado', 'dcf': 'FCD (FCFE)', 'graham': 'Graham com margem'}
KEYS = {'price', 'eps', 'bvps', 'dps', 'fcf_per_share', 'growth', 'terminal_growth',
        'dcf_years', 'desired_yield', 'safety_margin', 'historical_pe', 'historical_pb',
        'discount_rate', 'graham_factor'}

def historical(rows):
    # Uma observação por dia de coleta: salvar repetidamente não aumenta seu peso.
    days = {}
    for row in rows:
        a = row['asset']
        stamp = a.get('sources', {}).get('price', {}).get('fetched_at') or row['created_at']
        days.setdefault(stamp[:10], a['data'])
    result = {}
    for name, denominator in [('pe', 'eps'), ('pb', 'bvps')]:
        samples = [d['price']/d[denominator] for d in days.values()
                   if d.get('price', 0) and d.get(denominator) and d['price'] > 0 and d[denominator] > 0]
        dates = sorted(day for day, d in days.items() if d.get('price') and d.get(denominator) and d['price'] > 0 and d[denominator] > 0)
        result[name] = {'value': mean(samples) if len(samples) >= 2 else None, 'count': len(samples),
                        'start': dates[0] if dates else None, 'end': dates[-1] if dates else None}
    return result

def defaults(asset, rows):
    d = dict(DEFAULTS, **asset['data'])
    h = historical(rows)
    values = {k: d.get(k) for k in KEYS}
    values.update(historical_pe=h['pe']['value'], historical_pb=h['pb']['value'],
                  discount_rate=calculate(d)['indicators']['discount_rate'], graham_factor=15)
    return {'inputs': values, 'historical': h, 'sources': asset.get('sources', {})}

def run(inputs):
    if not isinstance(inputs, dict) or set(inputs) - KEYS:
        raise ValueError('Campos de cálculo inválidos.')
    d = validate({k: v for k, v in inputs.items() if k not in {'historical_pe', 'historical_pb', 'discount_rate', 'graham_factor'}})
    for k in ('historical_pe', 'historical_pb', 'discount_rate', 'graham_factor'):
        v = inputs.get(k)
        if v is None or v == '':
            d[k] = None
            continue
        if isinstance(v, bool):
            raise ValueError(f'{k}: número inválido.')
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f'{k}: número inválido.')
        if not math.isfinite(v) or not 0 < v <= 10000:
            raise ValueError(f'{k}: informe um número positivo até 10000.')
        d[k] = v
    engine = dict(d, ipca=0, real_return=d['discount_rate'], rate_mode='additive',
                  target_pe=d['historical_pe'], target_pb=d['historical_pb'])
    a = calculate(engine)
    factor, eps, bvps = (d.get(k) for k in ('graham_factor', 'eps', 'bvps'))
    graham = math.sqrt(factor*eps*bvps) if all(v is not None and v > 0 for v in (factor, eps, bvps)) else None
    raw = {'pe_history': a['values']['pe_target'], 'pb_history': a['values']['pb_target'],
           'bazin': a['values']['bazin'], 'dcf': a['values']['dcf'], 'graham': graham}
    results = {}
    for key, value in raw.items():
        margin = d.get('safety_margin')
        ceiling = value * (1-margin/100) if value is not None and margin is not None else None
        price = d.get('price')
        results[key] = {'value': value, 'ceiling': ceiling,
                        'potential': (ceiling/price-1)*100 if ceiling is not None and price else None}
    return {'version': 1, 'inputs': d, 'results': results}
