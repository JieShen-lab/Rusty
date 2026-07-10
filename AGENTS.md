# Rusty Repository Instructions

## Scope

This repository is the Rusty local novel-processing application. Keep work scoped to the requested feature or verification task and preserve unrelated user changes.

## Product Rules

- Use Chinese-first product copy and a calm, light Apple-like visual direction for user-facing UI.
- Keep DOCX as an import format. DOCX export is out of scope unless the user explicitly reopens it.
- Do not silently broaden a stage into a large redesign or unrelated refactor.
- Keep SQLite writes explicit: commit on success, roll back on failure, and close connections on every path.

## Architecture Routing

- `src/rusty/`: Python domain models, persistence, import/export, services, and PySide UI.
- `backend/`: local API and schemas used by the newer desktop surface.
- `desktop/`: Electron/React/TypeScript UI.
- `tests/`: Python service, API, persistence, importer/exporter, and offscreen UI coverage.
- `PLAN.md`: locked implementation decisions and scope boundaries. Read it before extending the structured style, anchor, rewrite, or export-plan work.

## Data And Secret Safety

- Never commit `.venv/`, `desktop/node_modules/`, temporary `tmp*` folders, databases, logs, build output, or generated exports.
- Rusty's main database lives under `%LOCALAPPDATA%\Rusty\rusty.db`; it is not part of this repository.
- API secrets live in the operating-system keyring. Do not copy secrets into source files, logs, handoff documents, or Git history.
- Preserve backward compatibility for existing SQLite databases and add migration tests for schema changes.

## Working Discipline

1. Start with `git status --short --branch` and inspect the relevant diff.
2. Work in small verified phases; add focused tests for changed behavior.
3. Stage only files that belong to the task.
4. After a completed and verified change, commit and push the current branch to GitHub unless the user explicitly says not to push.
5. If the user asks to stop or asks for current progress, stop implementation and provide a concise verified status report.

## Verification

Run checks proportional to the change from `D:\Code\Rusty`:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
.\.venv\Scripts\python -m compileall src backend tests
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python -m unittest discover -s tests -p "test_ui_main_window.py"
npm --prefix desktop run build
git diff --check
```

Use the Python checks for backend/domain changes, the offscreen check for PySide changes, and the npm build whenever desktop API types or React/Electron UI code changes.
