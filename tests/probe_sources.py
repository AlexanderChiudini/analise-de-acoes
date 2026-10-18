import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from providers import fetch
for url in ['https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2265/p/last%201']:
    try:
        print(url, fetch(url)[:1200], flush=True)
    except Exception as e:
        print(type(e).__name__, str(e), flush=True)
