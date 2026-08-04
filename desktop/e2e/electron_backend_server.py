from __future__ import annotations

import os
import runpy
from pathlib import Path

os.environ["RUSTY_E2E_RUNTIME_NAME"] = "electron-e2e"
os.environ["RUSTY_API_PORT"] = "8767"
os.environ["RUSTY_API_TOKEN"] = "electron-e2e-token"
os.environ["RUSTY_API_ALLOWED_ORIGINS"] = "http://127.0.0.1:5173,null"

runpy.run_path(
    str(Path(__file__).with_name("real_backend_server.py")),
    run_name="__main__",
)
