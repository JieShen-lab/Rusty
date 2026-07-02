# Rusty UI-R2

UI-R2 adds a parallel Electron + React frontend and a FastAPI adapter layer. The existing PySide6 app, SQLite schema, importers, exporters, and service layer stay in place.

## What Was Added
- `design-system/MASTER.md` and page-level specs for the UI-R2 visual system.
- `backend/` FastAPI adapter layer over existing Rusty services.
- `desktop/` Electron + React + Vite + TypeScript + Tailwind frontend.

## Install Python API Dependencies

```powershell
pip install -e ".[ui-r2]"
```

The old PySide6 entry remains:

```powershell
python -m rusty
```

## Start Backend

Use a shared local token for mutating/path-based endpoints:

```powershell
$env:RUSTY_API_TOKEN="local-dev-token"
python -m backend.server
```

Defaults:
- Host: `127.0.0.1`
- Port: `8765`
- Health: `http://127.0.0.1:8765/api/health`

Optional:

```powershell
$env:RUSTY_DATABASE_PATH="D:\path\to\rusty.db"
$env:RUSTY_API_ALLOWED_ORIGINS="http://127.0.0.1:5173,http://localhost:5173"
```

If `RUSTY_API_TOKEN` is not set, the backend prints a temporary token at startup. Set the same value as `VITE_RUSTY_API_TOKEN` before running the frontend if you need preview/create/delete/export.

## Start Frontend

```powershell
cd desktop
npm install
$env:VITE_RUSTY_API_URL="http://127.0.0.1:8765"
$env:VITE_RUSTY_API_TOKEN="local-dev-token"
npm run dev
```

## Start Electron

In another terminal:

```powershell
cd desktop
$env:VITE_RUSTY_API_URL="http://127.0.0.1:8765"
$env:VITE_RUSTY_API_TOKEN="local-dev-token"
npm run electron:dev
```

UI-R2 does not auto-launch the Python backend. Start `python -m backend.server` manually first.

## UI-R2 Pages
- `/home`: dashboard with project metrics and recent projects.
- `/library`: project list, project detail, delete, workspace entry.
- `/workspace/:projectId`: project-bound chapter workspace, AI output preview, TXT/EPUB export.
- `/new-project`: local path preview/create minimal flow.
- `/models`: list-only model configuration entry; API keys are never returned.
- `/prompts`: list-only prompt template entry.

## Security Notes
- FastAPI binds to `127.0.0.1` by default.
- CORS defaults to Vite dev origins only.
- Mutating endpoints and local-path endpoints require `X-Rusty-Token`.
- New Project create requires the preview token and validates the source file fingerprint.
- Export writes to a project `exports/` directory with generated safe filenames; renderer-supplied output paths are not accepted.

## Verify

Python tests:

```powershell
python -m unittest discover -s tests
```

Backend health:

```powershell
python -m backend.server
curl http://127.0.0.1:8765/api/health
```

Frontend build:

```powershell
cd desktop
npm install
npm run build
```

Electron dev:

```powershell
cd desktop
npm run electron:dev
```

## Out of Scope for UI-R2
- Removing PySide6.
- Production packaging.
- Full AI pipeline execution API.
- Frontend-side API key editing.
- Moving Python business logic into TypeScript.
