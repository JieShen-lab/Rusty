from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from rusty.db import initialize_database_file  # noqa: E402
from rusty.services import AnchorService, ProjectService, PromptService  # noqa: E402


def seed_demo(
    database_path: str | Path,
    workspace_path: str | Path,
    *,
    example_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(example_path) if example_path is not None else Path(__file__).resolve().parent
    database = Path(database_path)
    workspace = Path(workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)
    initialize_database_file(database)

    rewrite_package = (root / "rewrite_prompt.json").read_text(encoding="utf-8")
    project_anchor = json.loads((root / "project_anchor.json").read_text(encoding="utf-8"))

    project_service = ProjectService(database)
    project_id = project_service.import_book(root / "source.txt", workspace)
    prompt_id = PromptService(database).import_template_text(rewrite_package)

    anchor_service = AnchorService(database)
    outline_id = anchor_service.create_outline_template(
        name=project_anchor["name"],
        description=project_anchor.get("description", ""),
        detail_level=project_anchor.get("detail_level", "standard"),
        outline=project_anchor.get("outline", {}),
        anchor_prompt=project_anchor.get("anchor_prompt", ""),
        source_metadata={"source_type": "example", "example": "xianxia"},
    )
    anchor_service.bind_project_outline(project_id, outline_id)

    project_service.update_project_settings(
        project_id,
        prompt_template_id=prompt_id,
        processing_mode="rewrite",
        concurrency=1,
        rewrite_mode="anchor_expand",
        max_attempts=2,
    )
    return {
        "project_id": project_id,
        "prompt_template_id": prompt_id,
        "outline_template_id": outline_id,
        "database_path": str(database.resolve()),
        "workspace_path": str(workspace.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Rusty xianxia prompt-compilation demo.")
    parser.add_argument("--database", required=True, help="SQLite database path for the isolated demo.")
    parser.add_argument("--workspace", required=True, help="Workspace directory for the imported demo project.")
    arguments = parser.parse_args()
    result = seed_demo(arguments.database, arguments.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
