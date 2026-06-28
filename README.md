# Rusty

Python + PySide6 + SQLite desktop app for local novel project parsing, preview, and export.

## MVP Scope

- Import TXT
- Parse chapters
- Save projects and chapter metadata in SQLite
- Preview chapters
- Export TXT

EPUB / DOCX import and EPUB export are planned for the next phase.

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
- `src/rusty/importers/txt.py`: TXT encoding detection and chapter splitting
- `src/rusty/services/project_service.py`: project persistence and TXT export workflow
- `src/rusty/db/connection.py`: SQLite connection defaults
- `src/rusty/db/schema.py`: schema creation and seed data
- `tests/test_schema.py`: schema smoke tests
- `tests/test_txt_importer.py`: TXT parsing and export tests
