# Plan: Rusty UI-R2 Electron + React + Python API Migration
_Locked via grill by Claude + user_

## Goal
Build the first parallel Web UI architecture for Rusty without rewriting the existing Python business layer. UI-R2 will introduce an Electron shell, a React + Vite + TypeScript + Tailwind frontend, and a FastAPI adapter layer over the existing Rusty services. The legacy PySide6 entrypoint and service/database model remain intact. The first validated user flows are: Home dashboard, Library project browsing, Project Workspace chapter viewing, and a minimal New Project flow that supports preview plus create.

## Approach
1. Add planning artifacts required by grill-me-codex, then keep implementation bounded to the locked route model: `/home`, `/library`, `/workspace/:projectId`, `/new-project`, `/models`, `/prompts`. `/new-project` may be presented as a route-backed page or route-backed modal, but it must be deep-linkable enough for implementation and testing.
2. Create a persisted design system under `design-system/` with one master spec and page-level specs for `home`, `project-workspace`, `new-project`, `models`, and `prompts`, using an Obsidian-inspired dark glassmorphism creative workspace direction.
3. Add a `backend/` FastAPI adapter layer with shared response schemas and minimal endpoints for health, project list/detail, chapter list/detail, delete project, new-project preview/create, TXT export, and EPUB export. Reuse existing Rusty services rather than moving business logic into the API layer. API reads/exports must hide soft-deleted projects even if legacy service methods remain permissive.
4. Add a new `desktop/` Electron + React + Vite + TypeScript + Tailwind app with secure Electron main/preload files, API client wrappers, theme styles, reusable glassmorphism components, and page shells matching the design system. Electron security settings are acceptance criteria: `contextIsolation: true`, `nodeIntegration: false`, no remote module usage, denied unexpected navigation/window-open, and a typed allowlisted preload API.
5. Implement real backend integration for `HomePage`, `WorkbenchPage` (Library), `ProjectWorkspacePage`, and a minimal `NewProjectPage` flow using preview plus create. `ModelsPage` and `PromptsPage` must either use list-only APIs from the existing services or be clearly marked as non-editing UI-R2 placeholders; they must not imply fake persisted state.
6. Preserve the existing PySide6 app and tests. Add new backend and frontend files in parallel, avoid database schema changes, and document startup for backend, frontend, and Electron in `README_UI_R2.md`.
7. Verify: existing PySide6 entry import path still works, backend health endpoint responds, Electron frontend can start, and Python tests still pass.

## Backend API constraints
- The FastAPI server must bind to `127.0.0.1` by default, not `0.0.0.0`. CORS must not be broad; allow only the Vite dev origin and Electron production origin/file context required by UI-R2. Mutating endpoints and any endpoint accepting local file paths must require an app-generated local session token supplied by the Electron/React client. This is local IPC protection, not user authentication.
- Project and chapter routes are project-bound. Prefer `/api/projects/{project_id}/chapters/{chapter_id}` for chapter detail so the API can verify the chapter belongs to the requested non-deleted project. A global `/api/chapters/{chapter_id}` may exist only as a compatibility helper if it performs the same ownership and soft-delete checks.
- API list/detail/chapter/export endpoints must not expose projects where `projects.deleted_at IS NOT NULL`. This is an API boundary rule and does not require changing legacy `ProjectService` behavior or tests.
- The adapter layer should avoid direct SQL, but it may add narrow read-only ownership/soft-delete checks when existing services expose deleted or globally addressed records. Such SQL must remain in the adapter boundary and not become new business logic.
- Errors must be normalized as JSON with stable `error`, `message`, and optional `details` fields. Map expected failures explicitly: unsupported file format and validation errors to `400`, missing files/projects/chapters and deleted projects to `404`, export filesystem failures to `500`, and not-yet-wired AI endpoints to `501`.
- Blocking service calls should run safely under FastAPI. Configure SQLite `busy_timeout` for API connections where possible and keep write-heavy endpoints serialized or documented as single-writer for UI-R2.
- Python API dependencies must be declared in a named optional extra, for example `ui-r2 = ["fastapi", "uvicorn"]`, and documented in `README_UI_R2.md`.
- New Project API endpoints are explicit: `POST /api/projects/preview` accepts a validated local source path plus optional workspace path for UI-R2 local development, returns parsed metadata/chapter preview only, and issues a short-lived preview token tied to the absolute source path, file size, mtime, and content hash when practical. `POST /api/projects` must submit that token plus optional workspace/project name, revalidate the file fingerprint before calling the existing preview/create/import service flow, and return the created project. If IPC file selection is not completed in UI-R2, the UI must label path entry as local development preview rather than browser upload.

## File and export safety
- The renderer must not provide arbitrary local paths directly. UI-R2 may keep backend-driven path text inputs for early validation only if documented as local-development-only; the preferred route is Electron file selection through a typed preload IPC that returns validated absolute paths selected by the user.
- The minimal new-project flow must keep preview and create tied to the same selected source path. It must not pretend that browser file upload bytes are supported unless the backend actually implements upload persistence.
- Export endpoints must not accept renderer-controlled arbitrary output paths. UI-R2 exports write under a deterministic project export directory, such as `<project_workspace>/exports/`, using sanitized filenames like `<safe_project_name>-<timestamp>.txt` or `.epub`. No silent overwrite is allowed; if a generated file exists, append a numeric suffix or return a clear conflict. Electron save-dialog export can be deferred to UI-R3.

## Verification requirements
- Keep the existing Python test suite green.
- Add or document API smoke checks for `/api/health`, project list/detail, chapter list/detail, new-project preview/create, deleted-project handling, export response/error handling, and not-yet-wired AI placeholder responses.
- Include API security smoke checks for loopback binding expectations, restricted CORS configuration, token rejection on mutating/path-based endpoints, and preview-token mismatch/expiry.
- Add at least one frontend flow check, manual or automated, covering Library project selection into `/workspace/:projectId`, `/new-project` selected path -> preview -> create -> library/workspace visibility, and request-level loading/error/empty states.
- Add a static or testable check for Electron BrowserWindow security options.

## Key decisions & tradeoffs
- Route model is project-bound, not global-state-only: `workspace/:projectId` is the canonical workspace route for refresh recovery and future deep linking.
- `NewProjectPage` is a minimal closed loop in UI-R2: preview plus create only. It does not recreate the full six-step PySide6 wizard yet.
- Backend run mode for UI-R2 is manual startup. Electron does not auto-launch Python yet.
- Because the user chose option B for runtime behavior, the frontend will not block on a dedicated startup error page if backend health fails. API failures still need clear loading/error presentation at request points.
- Legacy PySide6 UI remains as a parallel entrypoint rather than being removed or replaced in-place.
- Models and Prompts are lower-priority surfaces in UI-R2 and may ship as static or read-only shells if full CRUD API wiring threatens scope.

## Risks / open questions
- The user-selected runtime mode B reduces explicit startup guidance, so backend-unavailable states must still be surfaced clearly enough in request-driven UI flows to avoid silent failure.
- Minimal project creation depends on what information `ProjectService.preview_book()` and `create_project()` can supply without reintroducing the full wizard complexity.
- Electron dev startup depends on local Node/npm availability and installable frontend dependencies in this environment.
- Tailwind + Vite + Electron configuration must stay parallel to the Python package layout and not interfere with the existing test harness.

## Out of scope
- Rewriting `ProjectService`, `ModelService`, `PromptService`, or `PipelineService`
- Database schema changes
- Removing PySide6 UI or replacing the existing Python entrypoint
- Full production packaging
- Full AI pipeline API coverage beyond minimal placeholders or obvious existing adapters
- Moving business logic or secrets handling into the frontend
