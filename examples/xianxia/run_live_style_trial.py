from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from examples.xianxia.seed_demo import seed_demo
from rusty.services import PipelineService, ProjectService, StyleExtractionService, StyleTemplateService


def run_live_trial(
    database_path: Path,
    workspace_path: Path,
    output_path: Path,
    example_path: Path,
) -> dict[str, object]:
    seeded = seed_demo(database_path, workspace_path, example_path=example_path)
    project_id = seeded["project_id"]

    extraction = StyleExtractionService(database_path)
    style_template_id = extraction.extract_from_file(
        example_path / "style_source_excerpt.txt",
        name="古典斗法动作因果实测",
        detail_level="detailed",
    )
    StyleTemplateService(database_path).bind_project_style(project_id, style_template_id)

    result = PipelineService(database_path).run_project(project_id)
    chapter = ProjectService(database_path).list_chapters(project_id)[0]
    style = StyleTemplateService(database_path).get_template(style_template_id)
    if style is None:
        raise RuntimeError("Style extraction completed without a saved style template.")

    artifact = {
        "project_id": project_id,
        "style_template_id": style_template_id,
        "pipeline": {
            "processed": result.processed,
            "skipped": result.skipped,
            "failed": result.failed,
        },
        "style_source": (example_path / "style_source_excerpt.txt").read_text(encoding="utf-8"),
        "extracted_style": json.loads(StyleTemplateService(database_path).export_template(style_template_id)),
        "bland_source": chapter.original_text,
        "model_rewrite": chapter.rewritten_text,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the xianxia public-domain style extraction and rewrite trial with a configured API model."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--example", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    artifact = run_live_trial(
        args.database.resolve(),
        args.workspace.resolve(),
        args.output.resolve(),
        args.example.resolve(),
    )
    print(
        json.dumps(
            {
                "project_id": artifact["project_id"],
                "style_template_id": artifact["style_template_id"],
                "pipeline": artifact["pipeline"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
