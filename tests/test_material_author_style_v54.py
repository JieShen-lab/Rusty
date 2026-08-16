from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from rusty.db import session
from rusty.db.schema import CURRENT_SCHEMA_VERSION, _migrate_to_v54, initialize_database_file
from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.anchor_extraction_service import AnchorExtractionService
from rusty.services.material_service import MaterialService, compile_material_ai_prompt
from rusty.services.model_service import ModelService


class DimensionAI(AIClient):
    def chat(self, model, api_key, messages):
        return AIResponse(
            text=json.dumps({
                "id": "dialogue", "analysis": "对话短促。",
                "features": ["省略主语"], "examples": ["走。"],
            }, ensure_ascii=False),
            token_usage={}, elapsed_ms=1,
        )


def test_v54_migrates_scene_materials_categories_filters_and_links_without_loss() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        database = Path(directory) / "rusty.db"
        initialize_database_file(database)
        with session(database) as connection:
            connection.execute("DELETE FROM schema_migrations WHERE version = 54")
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DROP TABLE material_tag_links")
            connection.execute("DROP TABLE material_category_links")
            connection.execute("ALTER TABLE materials RENAME TO materials_current")
            connection.execute("""
                CREATE TABLE materials AS SELECT * FROM materials_current WHERE 0
            """)
            connection.execute("INSERT INTO projects(id, name) VALUES (1, 'P')")
            connection.execute("""
                INSERT INTO materials(id, material_type, scope, name, description, raw_text,
                    content_json, source_metadata_json, import_metadata_json, analysis_status,
                    detail_level, sort_order, version, created_at, updated_at)
                VALUES (7, 'scene_reference', 'public', 'Legacy', 'D', 'SOURCE',
                    '{"summary":"old"}', '{"origin":"x"}', '{"audit":true}', 'analyzed',
                    'standard', 3, 4, '2025-01-01', '2025-02-01')
            """)
            connection.execute("DROP TABLE materials_current")
            connection.execute("DROP TABLE material_categories")
            connection.execute("CREATE TABLE material_categories(id INTEGER PRIMARY KEY, material_type TEXT, name TEXT, normalized_name TEXT, sort_order INTEGER, created_at TEXT, updated_at TEXT, deleted_at TEXT)")
            connection.execute("INSERT INTO material_categories VALUES(5, 'scene_reference', 'Style', 'style', 0, 'a', 'b', NULL)")
            connection.execute("CREATE TABLE material_tag_links(material_id INTEGER, tag_id INTEGER, created_at TEXT)")
            connection.execute("CREATE TABLE material_category_links(material_id INTEGER, category_id INTEGER, created_at TEXT)")
            connection.execute("INSERT INTO material_category_links VALUES(7, 5, 'c')")
            connection.execute("DROP TABLE project_material_filter_tags")
            connection.execute("DROP TABLE project_material_filters")
            connection.execute("CREATE TABLE project_material_filters(id INTEGER PRIMARY KEY, project_id INTEGER, material_type TEXT, match_mode TEXT, manual_material_ids_json TEXT, include_scene_keywords INTEGER, include_applicable_scene_tags INTEGER, created_at TEXT, updated_at TEXT)")
            connection.execute("INSERT INTO project_material_filters VALUES(9, 1, 'scene_reference', 'all', '[7]', 1, 1, 'a', 'b')")
            connection.execute("CREATE TABLE project_material_filter_tags(filter_id INTEGER, tag_id INTEGER, created_at TEXT)")
            connection.execute("DROP TABLE material_ai_settings")
            _migrate_to_v54(connection)
            _migrate_to_v54(connection)
            row = connection.execute("SELECT * FROM materials WHERE id = 7").fetchone()
            assert row["material_type"] == "author_style"
            assert row["raw_text"] == "SOURCE"
            assert row["created_at"] == "2025-01-01"
            content = json.loads(row["content_json"])
            assert content["legacy_scene_reference"] == {"summary": "old"}
            assert connection.execute("SELECT COUNT(*) FROM material_category_links WHERE material_id=7 AND category_id=5").fetchone()[0] == 1
            assert connection.execute("SELECT material_type FROM material_categories WHERE id=5").fetchone()[0] == "author_style"
            filter_row = connection.execute("SELECT material_type, manual_material_ids_json FROM project_material_filters WHERE id=9").fetchone()
            assert tuple(filter_row) == ("author_style", "[7]")


def test_current_types_settings_and_author_style_json_round_trip() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        service = MaterialService(Path(directory) / "rusty.db")
        initialize_database_file(service.database_path)
        assert CURRENT_SCHEMA_VERSION == 54
        assert {item.task_type for item in service.list_ai_settings()} == {
            "plot_skeleton_extraction", "author_style_extraction",
        }
        with pytest.raises(ValueError):
            service.create_material(material_type="scene_reference", scope="public", name="legacy")
        exported = service.export_author_style_settings()
        assert "model_id" not in exported
        assert "api_key" not in json.dumps(exported)
        exported["dimensions"] = [{"id": "women", "name": "女性描写风格", "requirement": "分析顺序。"}]
        imported = service.import_author_style_settings(exported)
        assert imported.dimensions[0]["id"] == "women"
        assert "女性描写风格" in compile_material_ai_prompt(imported)
        before = service.export_author_style_settings()
        with pytest.raises(ValueError):
            service.import_author_style_settings({"schema_version": 1, "config_type": "wrong", "dimensions": []})
        with pytest.raises(ValueError):
            service.import_author_style_settings({**before, "dimensions": ["not-an-object"]})
        with pytest.raises(ValueError):
            service.import_author_style_settings({**before, "dimensions": [{"id": "x", "name": "X", "requirement": 1}]})
        assert service.export_author_style_settings() == before


def test_author_style_single_dimension_preview_and_apply_only_updates_target() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        database = Path(directory) / "rusty.db"
        initialize_database_file(database)
        ModelService(database).create_model(
            display_name="Fake", provider="openai_compatible",
            base_url="https://example.invalid/v1", model_name="fake", is_default=True,
        )
        materials = MaterialService(database)
        material_id = materials.create_material(
            material_type="author_style", scope="public", name="Writer", raw_text="走。她停下。",
            content={"schema_version": 1, "summary": "", "dimensions": [
                {"id": "sentence", "name": "句子", "requirement": "句式", "analysis": "短句", "features": ["短"], "examples": ["走。"]},
                {"id": "dialogue", "name": "对话", "requirement": "对白", "analysis": "", "features": [], "examples": []},
            ]},
        )
        extraction = AnchorExtractionService(database, ai_client=DimensionAI())
        preview = extraction.preview_author_style_dimension(
            material_id, dimension_id="dialogue", dimension_name="对话", dimension_requirement="对白",
        )
        assert preview["features"] == ["省略主语"]
        updated = extraction.apply_author_style_dimension(material_id, preview_token=preview["preview_token"])
        updated_content = json.loads(updated.content_json)
        assert updated_content["dimensions"][0]["analysis"] == "短句"
        assert updated_content["dimensions"][1] == {
            "id": "dialogue", "name": "对话", "requirement": "对白",
            "analysis": "对话短促。", "features": ["省略主语"], "examples": ["走。"],
        }
        assert all("document_id" not in item and "chapter_id" not in item for item in updated_content["dimensions"])


def test_author_style_dimension_extraction_requires_source_and_rejects_stale_preview() -> None:
    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        database = Path(directory) / "rusty.db"
        initialize_database_file(database)
        ModelService(database).create_model(
            display_name="Fake", provider="openai_compatible",
            base_url="https://example.invalid/v1", model_name="fake", is_default=True,
        )
        materials = MaterialService(database)
        content = {"schema_version": 1, "summary": "", "dimensions": [
            {"id": "dialogue", "name": "对话", "requirement": "对白", "analysis": "", "features": [], "examples": []},
        ]}
        empty_id = materials.create_material(material_type="author_style", scope="public", name="Empty", content=content)
        extraction = AnchorExtractionService(database, ai_client=DimensionAI())
        with pytest.raises(ValueError, match="没有保存可分析的来源文本"):
            extraction.preview_author_style_dimension(empty_id, dimension_id="dialogue", dimension_name="对话", dimension_requirement="对白")
        material_id = materials.create_material(material_type="author_style", scope="public", name="Writer", raw_text="走。", content=content)
        preview = extraction.preview_author_style_dimension(material_id, dimension_id="dialogue", dimension_name="对话", dimension_requirement="对白")
        material = materials.get_material(material_id)
        assert material is not None
        materials.update_material(
            material_id, name=material.name, description=material.description, detail_level=material.detail_level,
            raw_text="来源已改变。", content=json.loads(material.content_json), analysis_status=material.analysis_status,
            timeline_start_chapter=None, timeline_end_chapter=None, sort_order=material.sort_order,
        )
        with pytest.raises(ValueError, match="Source text changed"):
            extraction.apply_author_style_dimension(material_id, preview_token=preview["preview_token"])
