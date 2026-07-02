from __future__ import annotations

import os

import uvicorn

from .api import app, current_api_token


def main() -> None:
    host = os.environ.get("RUSTY_API_HOST", "127.0.0.1")
    port = int(os.environ.get("RUSTY_API_PORT", "8765"))
    if "RUSTY_API_TOKEN" not in os.environ:
        print("RUSTY_API_TOKEN was not set; generated a temporary UI-R2 token for this process:")
        print(current_api_token())
        print("Set the same value as VITE_RUSTY_API_TOKEN before running the Electron UI.")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
