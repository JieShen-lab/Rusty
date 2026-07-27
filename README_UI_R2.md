# Rusty UI-R2

UI-R2 is the actively developed Electron + React desktop application. FastAPI exposes the local API, while the Python service layer and SQLite v14 database own persistence and business logic. The earlier PySide6 entry remains available for compatibility.

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

## Start Backend Manually

Electron starts the Python backend automatically. Use this manual mode only when debugging the API without Electron, or when you want to attach logs directly:

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

If `RUSTY_API_TOKEN` is not set, the backend prints a temporary token at startup. Set the same value as `VITE_RUSTY_API_TOKEN` before running the standalone frontend if you need preview/create/delete/export.

## Start Frontend

```powershell
cd desktop
npm install
$env:VITE_RUSTY_API_URL="http://127.0.0.1:8765"
$env:VITE_RUSTY_API_TOKEN="local-dev-token"
npm run dev
```

## Start Electron

Electron will probe `http://127.0.0.1:8765/api/health`. If no Rusty backend is already running, it starts:

```powershell
.venv\Scripts\python.exe -m backend.server
```

from the repository root with an internal session token and closes that child process when Electron exits.

```powershell
cd desktop
npm run electron:dev
```

If you intentionally run the backend yourself, set the same token before launching Electron:

```powershell
cd desktop
$env:RUSTY_API_TOKEN="local-dev-token"
$env:VITE_RUSTY_API_URL="http://127.0.0.1:8765"
$env:VITE_RUSTY_API_TOKEN="local-dev-token"
npm run electron:dev
```

## UI-R2 Pages
- `/library`: project list, project detail, delete, workspace entry.
- `/workspace/:projectId`: project-bound rewrite/extraction workspace and export.
- `/new-project`: sequential import, split, preview, model, prompt, and confirmation flow.
- `/models`: model create/update/delete/test connection; API keys are accepted only as write-only inputs and are never returned.
- `/prompts`: rewrite and analysis prompt template management.
- `/outlines`: plot-outline template management and AI extraction.
- `/materials`: public/project scene materials and plot skeletons, tags, copies, and analysis state.
- `/characters`: public/project character cards, fixed/custom fields, tags, copies, and analysis state.
- `/documents`: document tags, editable content, revisions, merge, chapter creation, regex split, cleanup, and export.

## Migrated Functional Entrypoints

- Project library: list, detail, delete.
- Project workspace: chapter list/detail, AI output diagnostics, TXT/EPUB export.
- Chapter actions: summarize, detect scene, rewrite, retry rewrite, save manual rewrite, clear rewrite.
- Project actions: run project pipeline, pause project pipeline.
- Project settings API: model, prompt template, concurrency, target word count, and minimum expansion ratio.
- Models: create, update, delete, test connection.
- Prompts: create, update, delete.
- Resource tags: independent material, character, and document tag namespaces.
- Selection capture: save selected document/project text as a scene material, plot skeleton, or public character card.

## Security Notes
- FastAPI binds to `127.0.0.1` by default.
- CORS defaults to Vite dev origins only.
- Mutating endpoints and local-path endpoints require `X-Rusty-Token`.
- New Project create requires the preview token and validates the source file fingerprint.
- Export writes to a project `exports/` directory with generated safe filenames; renderer-supplied output paths are not accepted.

## Verify

Python tests:

```powershell
python -m pytest -q
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

## Current Boundaries

- PySide6 compatibility code is still present, but new product work targets Electron.
- Custom character-cover file upload is not connected yet; deterministic default covers are available.
- AI chapter splitting and the complete manual chapter-marking UI are not connected yet.
- Production installer packaging and code signing are not included.
- Python remains the source of truth for business logic; TypeScript does not duplicate the service layer.
