"""Entrypoint de Vercel Functions; não inicia servidor nem escreve no filesystem."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler

class handler(Handler):
    pass
