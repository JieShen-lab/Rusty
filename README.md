# Rusty

Python + PySide6 + SQLite desktop app for local novel project parsing, preview, and export.

## MVP Scope

- Import TXT / EPUB / DOCX
- Parse chapters
- Save projects and chapter metadata in SQLite
- Preview chapters
- Export TXT / EPUB

## Development

Create an environment and install the project:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e .
```

Run the app:

```powershell
.\.venv\Scripts\rusty
```

The MVP app stores its local database at:

```text
%USERPROFILE%\AppData\Local\Rusty\rusty.db
```

Model API keys are not stored in the main SQLite database. Rusty stores a
keyring reference in `ai_models.api_key_secret_ref` and writes the secret value
to the operating system keyring through the `keyring` package.

The AI pipeline uses OpenAI-compatible `/chat/completions` APIs through `httpx`.
Current stages include chapter summary, scene detection, chapter rewrite,
error recording, retry entry points, project pause status, and merged text
output. Project-level AI settings can bind a model and prompt template, and the
pipeline falls back to global defaults when a project has no explicit binding.

Run tests without installing the package:

```powershell
python -m unittest discover -s tests
```

Initialize a SQLite database from source:

```powershell
$env:PYTHONPATH = "src"
python -m rusty.db.schema rusty.db
```

## Current Structure

- `src/rusty/app.py`: minimal PySide6 application entry point
- `src/rusty/importers/`: TXT / EPUB / DOCX parsing
- `src/rusty/exporters/`: TXT / EPUB export
- `src/rusty/services/project_service.py`: project persistence and import/export workflow
- `src/rusty/services/model_service.py`: model CRUD and keyring-backed API key references
- `src/rusty/services/prompt_service.py`: prompt template CRUD and project-level prompt overrides
- `src/rusty/services/pipeline_service.py`: AI summary, scene detection, rewrite, retry, pause, and merge workflow
- `src/rusty/ui/main_window.py`: PySide6 main window, workbench, new-project dialog, and chapter preview
- `src/rusty/db/connection.py`: SQLite connection defaults
- `src/rusty/db/schema.py`: schema creation and seed data
- `tests/test_schema.py`: schema smoke tests
- `tests/test_txt_importer.py`: TXT parsing and export tests
- `tests/test_epub_docx.py`: EPUB / DOCX parser and EPUB export tests
- `tests/test_project_service.py`: persistence and metadata tests
- `tests/test_model_prompt_services.py`: model, keyring-reference, prompt, and project-prompt tests
- `tests/test_pipeline_service.py`: fake-client AI pipeline tests
- `tests/test_ui_main_window.py`: offscreen UI smoke test
