from __future__ import annotations


STORY_ANCHOR_TYPES = frozenset(
    {
        "document_end",
        "chapter_start",
        "chapter_end",
        "scene_start",
        "scene_end",
        "skeleton_node",
        "text_offset",
        "branch_chapter",
        "branch_scene",
    }
)
BRANCH_CONTENT_ANCHOR_TYPES = frozenset({"branch_chapter", "branch_scene"})
ORIGINAL_ANCHOR_TYPES = STORY_ANCHOR_TYPES - BRANCH_CONTENT_ANCHOR_TYPES

BRANCH_GENERATION_MODES = frozenset({"open_continuation", "fork"})
GENERATION_MODE_RULES = {
    "bounded_insert": ("rewrite", "in_place", True),
    "open_continuation": ("branch", "branch", False),
    "fork": ("branch", "branch", False),
}
