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
- `src/rusty/db/connection.py`: SQLite connection defaults
- `src/rusty/db/schema.py`: schema creation and seed data
- `tests/test_schema.py`: schema smoke tests
