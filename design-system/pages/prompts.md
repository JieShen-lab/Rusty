# Prompts Page

## Purpose
UI-R2 Prompts is an entry point for prompt strategy. It may be list-only or clearly marked as a placeholder, but should preview real persisted template structure when available.

## Layout
- Header: 提示词.
- Left: template list cards with name, version, default marker.
- Right: tab-like preview for 全局规则, 总结规则, 场景识别, 改写规则.

## Data Rules
- Prefer list-only API from `PromptService.list_templates()`.
- Do not edit database schema.
- Do not create fake prompt templates if none exist.

## Visual Notes
- Treat prompt text like writing studio material: readable, strong panel opacity, generous line-height.
- Use gold for default template accents.
