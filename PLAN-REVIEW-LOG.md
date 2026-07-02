# Plan Review Log: Rusty UI-R2 Electron + React + Python API Migration
Act 1 (grill) complete - plan locked with the user. MAX_ROUNDS=5.

## Round 1 - Codex
Verdict: REVISE

Findings:
- Project-bound workspace was undercut by global chapter access; require project-bound chapter detail and ownership checks.
- Soft-deleted projects can still expose chapters through legacy service behavior; API must hide deleted projects for reads/exports.
- New Project preview/create needed a local file selection contract because `create_project()` re-reads the source path.
- Export endpoints could become arbitrary filesystem writes if they accept renderer-controlled paths.
- FastAPI/uvicorn dependency ownership was not declared.
- SQLite concurrency and `busy_timeout` were not addressed for overlapping API requests.
- Electron security constraints were not specific or testable.
- Verification did not prove real migrated flows.
- Error mapping from service exceptions to JSON responses was missing.
- Models/Prompts placeholders risked implying fake persisted state.

Response:
- Revised `PLAN.md` with project-bound and soft-delete API constraints, file/export safety rules, explicit HTTP error mapping, dependency declaration requirements, SQLite concurrency notes, Electron security acceptance criteria, and stronger verification requirements.

## Round 2 - Codex
Verdict: REVISE

Findings:
- The plan promised `NewProjectPage` preview/create, but the route and backend endpoint inventory omitted `/new-project`, preview, and create.
- Verification did not require exercising selected path -> preview -> create -> library/workspace visibility.
- Export safety did not define generated filenames, collision handling, or overwrite behavior while using service-level path writes.

Response:
- Revised `PLAN.md` to include `/new-project`, explicit `POST /api/projects/preview` and `POST /api/projects`, frontend/backend preview-create verification, and deterministic project export directory naming with no silent overwrite.

## Round 3 - Codex
Verdict: REVISE

Findings:
- Local FastAPI endpoints expose path preview/create, delete, and export without constraints for host binding, CORS, Origin handling, or a local session token.
- Preview stores no state while create accepts a fresh source path, so the API does not enforce preview/create binding.

Response:
- Revised `PLAN.md` to require loopback-only binding, restricted CORS, app-generated local tokens for mutating/path-based endpoints, and a short-lived preview token tied to source path and file fingerprint that create must revalidate.

## Round 4 - Codex
Verdict: APPROVED

Findings:
- No material blockers remain. Codex accepted the updated New Project routing/API inventory, local API security constraints, preview/create binding, export collision behavior, and verification coverage.
