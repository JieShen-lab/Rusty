from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from rusty.db.schema import _migrate_to_v55
from rusty.services.material_service import MaterialService


def test_v55_removes_character_assets_and_plot_materials_but_preserves_author_style() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE projects(id INTEGER PRIMARY KEY, deleted_at TEXT);
        CREATE TABLE ai_models(id INTEGER PRIMARY KEY);
        CREATE TABLE materials(
            id INTEGER PRIMARY KEY, material_type TEXT, scope TEXT, project_id INTEGER,
            name TEXT, description TEXT, detail_level TEXT, raw_text TEXT, content_json TEXT,
            analysis_status TEXT, source_metadata_json TEXT, import_metadata_json TEXT,
            source_material_id INTEGER, source_version INTEGER, legacy_outline_id INTEGER,
            timeline_start_chapter INTEGER, timeline_end_chapter INTEGER, sort_order INTEGER,
            version INTEGER, created_at TEXT, updated_at TEXT, deleted_at TEXT
        );
        CREATE TABLE material_tags(id INTEGER PRIMARY KEY, name TEXT, normalized_name TEXT,
            tag_group TEXT, sort_order INTEGER, created_at TEXT, updated_at TEXT, deleted_at TEXT);
        CREATE TABLE material_tag_links(material_id INTEGER, tag_id INTEGER, created_at TEXT);
        CREATE TABLE material_categories(id INTEGER PRIMARY KEY, material_type TEXT, name TEXT,
            normalized_name TEXT, sort_order INTEGER, created_at TEXT, updated_at TEXT, deleted_at TEXT);
        CREATE TABLE material_category_links(material_id INTEGER, category_id INTEGER, created_at TEXT);
        CREATE TABLE project_material_filters(id INTEGER PRIMARY KEY, project_id INTEGER,
            material_type TEXT, match_mode TEXT, manual_material_ids_json TEXT,
            include_scene_keywords INTEGER, include_applicable_scene_tags INTEGER,
            created_at TEXT, updated_at TEXT);
        CREATE TABLE project_material_filter_tags(filter_id INTEGER, tag_id INTEGER, created_at TEXT);
        CREATE TABLE material_ai_settings(task_type TEXT PRIMARY KEY, model_id INTEGER,
            detail_level TEXT, system_prompt TEXT, base_instruction TEXT, dimensions_json TEXT,
            extra_requirements TEXT, updated_at TEXT);
        CREATE TABLE character_cards(id INTEGER PRIMARY KEY);
        CREATE TABLE character_tags(id INTEGER PRIMARY KEY);
        CREATE TABLE character_tag_links(character_card_id INTEGER, tag_id INTEGER);
        CREATE TABLE character_categories(id INTEGER PRIMARY KEY);
        CREATE TABLE character_category_links(character_card_id INTEGER, category_id INTEGER);
        CREATE TABLE character_extraction_settings(id INTEGER PRIMARY KEY);
        CREATE TABLE project_character_bindings(project_id INTEGER, character_card_id INTEGER);
        INSERT INTO projects VALUES(1, NULL);
        INSERT INTO material_tags VALUES(1, 'style', 'style', 'general', 0, 'a', 'b', NULL);
        INSERT INTO materials VALUES
          (10, 'author_style', 'public', NULL, 'Writer', 'style', 'standard', 'SOURCE',
           '{"summary":"kept"}', 'analyzed', '{"document_id":2}', '{"audit":true}',
           NULL, NULL, NULL, NULL, NULL, 0, 4, 'a', 'b', NULL),
          (11, 'plot_skeleton', 'public', NULL, 'Plot', 'plot', 'standard', 'PLOT',
           '{"stages":[]}', 'analyzed', '{}', '{}', NULL, NULL, NULL, NULL, NULL, 0, 1, 'a', 'b', NULL);
        INSERT INTO material_tag_links VALUES(10, 1, 'a'), (11, 1, 'a');
        INSERT INTO material_categories VALUES
          (20, 'author_style', 'Style', 'style', 0, 'a', 'b', NULL),
          (21, 'plot_skeleton', 'Plot', 'plot', 0, 'a', 'b', NULL);
        INSERT INTO material_category_links VALUES(10, 20, 'a'), (11, 21, 'a');
        INSERT INTO project_material_filters VALUES
          (30, 1, 'author_style', 'any', '[10]', 1, 1, 'a', 'b'),
          (31, 1, 'plot_skeleton', 'any', '[11]', 1, 1, 'a', 'b');
        INSERT INTO material_ai_settings VALUES
          ('author_style_extraction', NULL, 'standard', 'style-system', 'style-base',
           '[{"id":"sentence","name":"句式","requirement":"分析句式"}]', '', 'b'),
          ('plot_skeleton_extraction', NULL, 'standard', 'plot-system', 'plot-base', '[]', '', 'b');
        INSERT INTO character_cards VALUES(1);
        """
    )

    _migrate_to_v55(connection)

    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "character_cards" not in tables
    assert "character_extraction_settings" not in tables
    assert [tuple(row) for row in connection.execute("SELECT id, raw_text, version FROM materials")] == [(10, "SOURCE", 4)]
    assert json.loads(connection.execute("SELECT source_metadata_json FROM materials").fetchone()[0]) == {"document_id": 2}
    assert [tuple(row) for row in connection.execute("SELECT material_id, tag_id FROM material_tag_links")] == [(10, 1)]
    assert [tuple(row) for row in connection.execute("SELECT material_id, category_id FROM material_category_links")] == [(10, 20)]
    assert [tuple(row) for row in connection.execute("SELECT task_type FROM material_ai_settings")] == [("author_style_extraction",)]
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO materials(id, material_type, scope, name) VALUES(99, 'plot_skeleton', 'public', 'x')"""
        )


def test_current_api_has_no_character_routes_and_material_service_rejects_plot(tmp_path) -> None:
    database = tmp_path / "rusty.db"
    app = create_app(database)
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(path.startswith("/api/characters") for path in paths)
    assert not any("character-modification-analysis" in path for path in paths)
    assert TestClient(app).get("/api/characters").status_code == 404
    with pytest.raises(ValueError, match="Unsupported material type"):
        MaterialService(database).create_material(
            material_type="plot_skeleton", scope="public", name="removed"
        )
