"""Motor financeiro puro. Taxas em pontos percentuais; valores por ação em BRL."""
import math

DEFAULTS = {'category': 'Não classificada', 'growth': 5.0, 'desired_yield': 8.0,
            'real_return': 9.0, 'safety_margin': 15.0, 'target_pe': 15.0,
            'target_pb': 1.0, 'terminal_growth': 3.0, 'dcf_years': 10,
            'rate_mode': 'additive', 'notes': '', 'quality': {}}
NUMERIC = {'price', 'dy', 'dps', 'eps', 'bvps', 'growth', 'ipca', 'desired_yield',
           'real_return', 'safety_margin', 'target_pe', 'target_pb', 'fcf_per_share',
           'terminal_growth', 'dcf_years'}
FIELDS = NUMERIC | {'category', 'rate_mode', 'notes', 'quality'}

def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Envie um objeto JSON.')
    out = {}
    for key, value in data.items():
        if key not in FIELDS:
            continue
        if key in NUMERIC:
            if value is None or value == '':
                out[key] = None
                continue
            if isinstance(value, bool):
                raise ValueError(f'{key}: número inválido.')
            try:
                n = float(value)
            except (TypeError, ValueError):
                raise ValueError(f'{key}: número inválido.')
            if not math.isfinite(n) or abs(n) > 1e15:
                raise ValueError(f'{key}: número fora do intervalo.')
            if key in {'price', 'dps', 'dy', 'desired_yield', 'real_return', 'target_pe', 'target_pb'} and n < 0:
                raise ValueError(f'{key} não pode ser negativo.')
            if key == 'price' and n == 0:
                raise ValueError('Preço deve ser positivo.')
            if key == 'safety_margin' and not 0 <= n < 100:
                raise ValueError('Margem deve estar entre 0 e 100%.')
            if key in {'growth', 'ipca', 'terminal_growth'} and not -99 < n < 100:
                raise ValueError(f'{key} deve estar entre -99 e 100%.')
            if key == 'dcf_years' and (n != int(n) or not 1 <= n <= 30):
                raise ValueError('Horizonte do fluxo deve ser inteiro entre 1 e 30 anos.')
            out[key] = n
        elif key == 'quality':
            if not isinstance(value, dict) or any(v not in ('yes', 'no', 'unknown') for v in value.values()):
                raise ValueError('Checklist qualitativo inválido.')
            out[key] = {str(k)[:80]: v for k, v in value.items()}
        elif key == 'rate_mode':
            if value not in ('additive', 'compound'):
                raise ValueError('Modo da taxa inválido.')
            out[key] = value
        elif isinstance(value, str):
            out[key] = value[:20000]
        else:
            raise ValueError(f'{key}: texto esperado.')
    return out

def calculate(d):
    def num(k):
        x = d.get(k)
        return float(x) if x is not None else None
    p, eps, bvps, dps = (num(k) for k in ('price', 'eps', 'bvps', 'dps'))
    growth, ipca, real = (num(k) for k in ('growth', 'ipca', 'real_return'))
    y, margin = num('desired_yield'), num('safety_margin')
    k = None
    if ipca is not None and real is not None:
        k = ((1 + ipca / 100) * (1 + real / 100) - 1) * 100 if d.get('rate_mode') == 'compound' else ipca + real
    vals, reasons = {}, {}
    def add(name, value, reason):
        vals[name] = value if value is not None and math.isfinite(value) else None
        if vals[name] is None:
            reasons[name] = reason
    add('bazin', dps / (y / 100) if dps is not None and dps >= 0 and y and y > 0 else None, 'Exige DPS e yield desejado positivo.')
    add('graham', math.sqrt(22.5 * eps * bvps) if eps is not None and bvps is not None and eps > 0 and bvps > 0 else None, 'Graham exige LPA e VPA positivos.')
    add('gordon', dps * (1 + growth / 100) / ((k - growth) / 100) if dps is not None and dps >= 0 and growth is not None and k is not None and k > growth else None, 'Exige DPS, IPCA e taxa de desconto maior que crescimento.')
    base = [vals[n] for n in ('bazin', 'graham', 'gordon') if vals[n] is not None]
    # A planilha usa os três modelos: não gerar sinal definitivo com um modelo faltante.
    complete = len(base) == 3
    add('conservative', min(base) if complete else None, 'Faltam modelos para comparar os três preços.')
    add('average', sum(base) / 3 if complete else None, 'A média exige os três modelos válidos.')
    add('safe_average', vals['average'] * (1 - margin / 100) if complete and margin is not None else None, 'Exige os três modelos e margem de segurança.')
    add('pe_target', eps * num('target_pe') if eps is not None and eps > 0 and num('target_pe') is not None else None, 'Exige LPA positivo e P/L alvo.')
    add('pb_target', bvps * num('target_pb') if bvps is not None and bvps > 0 and num('target_pb') is not None else None, 'Exige VPA positivo e P/VP alvo.')
    fcf, terminal, years = num('fcf_per_share'), num('terminal_growth'), num('dcf_years')
    dcf = None
    if fcf is not None and fcf > 0 and k is not None and k > 0 and terminal is not None and k > terminal and growth is not None and years:
        cash = [fcf * (1 + growth / 100) ** t / (1 + k / 100) ** t for t in range(1, int(years) + 1)]
        terminal_value = fcf * (1 + growth / 100) ** int(years) * (1 + terminal / 100) / ((k - terminal) / 100)
        dcf = sum(cash) + terminal_value / (1 + k / 100) ** int(years)
    add('dcf', dcf, 'Exige FCFE por ação positivo, horizonte, crescimento e taxa maior que crescimento terminal.')
    def divide(a, b):
        return a / b if a is not None and b is not None and b != 0 else None
    indicators = {'pe': divide(p, eps), 'pb': divide(p, bvps), 'dy_calculated': divide(dps * 100 if dps is not None else None, p),
                  'earnings_yield': divide(eps * 100 if eps is not None else None, p), 'payout': divide(dps * 100 if dps is not None else None, eps),
                  'roe_approx': divide(eps * 100 if eps is not None else None, bvps), 'discount_rate': k}
    potential = {key: (value / p - 1) * 100 if value is not None and p is not None and p > 0 else None for key, value in vals.items()}
    def signal(key):
        v = potential[key]
        return 'SEM DADOS' if v is None else ('ABAIXO DO TETO' if v > 0 else 'NO TETO' if abs(v) < 1e-8 else 'CARA')
    warnings = []
    if not complete:
        warnings.append('Análise incompleta: o sinal conservador e definitivo exige Bazin, Graham e Gordon válidos.')
    if indicators['payout'] is not None and indicators['payout'] > 100:
        warnings.append('Proventos superam o lucro por ação: avalie recorrência e eventos extraordinários.')
    if indicators['dy_calculated'] is not None and d.get('dy') is not None and abs(indicators['dy_calculated'] - d['dy']) > .3:
        warnings.append('DY informado diverge de DPS/preço. Confira datas-base e proventos.')
    return {'values': vals, 'reasons': reasons, 'potential': potential, 'indicators': indicators,
            'signal': signal('conservative'), 'final_signal': signal('safe_average'), 'warnings': warnings}
