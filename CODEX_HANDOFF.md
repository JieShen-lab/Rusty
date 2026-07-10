# Codex Handoff: Rusty

Prepared: 2026-07-10

## Repository

- Local path: `D:\Code\Rusty`
- Remote: `https://github.com/JieShen-lab/Rusty.git`
- Branch: `main`
- Latest feature baseline before the sync-preparation commit: `6ad84b2` (`Add export chapter sequencing`)
- Use `git rev-parse HEAD` and `git ls-remote --heads origin` for the authoritative current commit after transfer.

## Current State

Rusty is a local novel-processing application with three main surfaces:

- Python domain and PySide application under `src/rusty/`.
- Local API under `backend/`.
- Electron/React desktop UI under `desktop/`.

The staged plan in `PLAN.md` has implementation commits through the planned export-sequencing phase. Recent completed areas include:

- Style-template management, extraction, and trial writing.
- Outline and character anchors with project binding and rewrite injection.
- Backend and desktop management surfaces for anchors.
- AI extraction for outline and character anchors.
- Persistent chapter export ordering, titles, inclusion flags, and TXT/EPUB integration.

Do not restart these phases from scratch. Inspect the implementation and tests before proposing more work.

## Stable Boundaries

- Chinese-first, light Apple-like UI.
- DOCX export remains out of scope.
- Local databases and keyring secrets are not stored in Git.
- Existing database upgrades require explicit migration coverage.
- Completed work is normally verified, committed, and pushed phase by phase.

## New-Computer Intake

1. Read `AGENTS.md`, this file, `README.md`, and `PLAN.md`.
2. Confirm the branch, remote, local `HEAD`, and remote `main`.
3. Rebuild `.venv` and `desktop/node_modules` instead of trusting copied environments.
4. Run the verification commands in `AGENTS.md`.
5. Report the verified current state before modifying code.
6. Ask which follow-up has priority; do not infer a new feature from `PLAN.md` after its listed phases are already implemented.

## Machine-Local State

Copying `D:\Code\Rusty` does not copy `%LOCALAPPDATA%\Rusty\rusty.db` or operating-system keyring entries. If the user needs the same projects and model credentials on the second computer, transfer the database separately while Rusty is closed and re-enter API credentials through the application/keyring.
