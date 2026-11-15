"""L'API ne doit pas charger pandas : c'est ce qui allège sa mémoire et son démarrage
en production (où pandas n'est d'ailleurs pas installé, cf. requirements-prod.txt)."""
from __future__ import annotations

import subprocess
import sys


def test_api_does_not_import_pandas_or_numpy():
    code = ("import sys, api.main, scripts.manage_users\n"
            "print([m for m in ('pandas', 'numpy') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
