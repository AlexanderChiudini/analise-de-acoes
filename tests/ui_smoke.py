"""Smoke test opcional no Edge headless, sem dependências ou dados reais."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import discovery
from models import DEFAULTS

ROOT = Path(__file__).resolve().parents[1]
EDGE = Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe'


class SmokeHandler(server.Handler):
    def route_get(self):
        if '/api/automatic/discovery/' in self.path and 'legacy=1' in self.headers.get('Referer', ''):
            return self.send(404, {'error': 'Rota não encontrada.'})
        if self.path == '/smoke.js':
            return self.send(200, (ROOT/'tests/ui_smoke.js').read_bytes(), 'text/javascript; charset=utf-8')
        if self.path.split('?', 1)[0] == '/':
            page = (ROOT/'static/index.html').read_text(encoding='utf-8')
            page = page.replace('</head>', '<script defer src="/smoke.js"></script></head>')
            return self.send(200, page.encode(), 'text/html; charset=utf-8')
        return super().route_get()


if __name__ == '__main__':
    if not EDGE.exists():
        raise SystemExit('Edge não encontrado; este teste é opcional.')
    with tempfile.TemporaryDirectory() as tmp:
        server.DB = Path(tmp)/'smoke.sqlite3'
        server.init()
        pagination = len(sys.argv) > 2 and sys.argv[2] == 'pagination'
        tickers = ['GOOD3', 'LOSS4', 'MISS3']
        if pagination:
            tickers += [f'P{chr(65+i//26)}{chr(65+i%26)}A3' for i in range(100)]
        for ticker in tickers:
            data = dict(DEFAULTS, company_name='Empresa de teste', price=10, eps=2, bvps=12, dy=8, dps=1, ipca=4)
            if ticker == 'LOSS4':
                data.update(eps=0.2)
            asset = {'ticker': ticker, 'data': data, 'extra': {'roe': 15, 'net_debt_ebitda': 2}, 'sources': {}, 'warnings': []}
            if ticker == 'MISS3':
                asset['extra'].pop('roe')
            server.save_asset(asset)
        # Fontes determinísticas para testar descoberta de empresas não cadastradas.
        discovery.universe = lambda: {'tickers': ['NEWC3', 'NEWL4', 'NEWM3'], 'source': 'Fixture B3', 'url': 'https://example.com/acoes', 'fetched_at': '2026-10-28T12:00:00+00:00'}
        discovery.inflation = lambda: ({'ipca': 4}, {}, {})
        def collect_candidate(ticker):
            data = {'price': 10, 'eps': 2, 'bvps': 12, 'dy': 8, 'dps': 1}
            extra = {'roe': 15, 'net_debt_ebitda': 2}
            if ticker == 'NEWL4':
                data['eps'] = 0.2
            if ticker == 'NEWM3':
                extra.pop('roe')
            return {'ticker': ticker, 'data': data, 'extra': extra, 'warnings': [], 'sources': {}}
        discovery.collect_candidate = collect_candidate
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), SmokeHandler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            width = int(sys.argv[1]) if len(sys.argv) > 1 else 1440
            legacy = len(sys.argv) > 2 and sys.argv[2] == 'legacy'
            output = ROOT/'.runtime'/f'automatic-{width}.png'
            result = subprocess.run([str(EDGE), '--headless', '--disable-gpu', '--no-first-run',
                '--no-default-browser-check', '--disable-extensions', '--disable-background-networking',
                '--disable-features=msEdgeSidebarV2', '--user-data-dir='+str(Path(tmp)/'profile'),
                '--window-size='+str(width)+',1000', '--virtual-time-budget=15000',
                '--screenshot='+str(output), '--dump-dom', f'http://127.0.0.1:{http.server_port}/'+('?legacy=1' if legacy else '?pagination=1' if pagination else '')],
                capture_output=True, timeout=50)
            dom = result.stdout.decode('utf-8', errors='replace')
            (ROOT/'.runtime'/f'automatic-{width}.html').write_text(dom, encoding='utf-8')
            if 'data-smoke="passed"' not in dom:
                print(dom[-2500:])
                print(result.stderr.decode('utf-8', errors='replace')[-2000:])
                raise SystemExit('Falha no smoke test do navegador.')
            print(json.dumps({'status': 'passed', 'width': width, 'screenshot': str(output)}))
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
