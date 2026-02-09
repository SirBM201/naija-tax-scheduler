# app/scheduler/__main__.py
from __future__ import annotations

import json
from .run_once import run_once

if __name__ == "__main__":
    result = run_once()
    print(json.dumps(result, indent=2))
