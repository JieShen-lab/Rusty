# Prompts Page

## Purpose
Prompts manages reusable rewrite and analysis strategies. FleshOut-derived observations remain reference material; Rusty rules are written and named independently.

## Layout
- Header: 提示词.
- Left: rewrite/analysis mode switch, create/import controls, template list, and default marker.
- Right: editable title, description, mode-specific tabs, rule editors, and structured output.
- Bottom: stable metadata/actions bar with one primary save action.

## Data Rules
- Templates are persisted through `PromptService`.
- Rewrite and analysis schemas stay distinct.
- Do not create fake templates if none exist.

## Visual Notes
- Use paper/canvas surfaces and the shared blue accent.
- Prompt text uses 14px type with generous line-height.
