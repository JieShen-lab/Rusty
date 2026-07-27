# Project Workspace Page

## Purpose
The workspace is the core writing and rewrite command center for one project. It must be project-bound through `/workspace/:projectId` and recover on refresh.

## Layout
- Header: 工程列表 return, chapter title, words/progress/save status, and panel visibility.
- Rewrite stages: 原文 / 剧情与人物 / 目标骨架 / 改写对照 / 导出检查.
- Extraction stages: 原文 / 章节风格分析 / 人工审查 / 全书归纳 / 提示词预览 / 导出 JSON.
- Three-column body on desktop:
  - Left: chapter navigation.
  - Center: chapter content and AI output.
  - Right: stats, progress, exports, errors.

## Chapter Navigation
- Show title, word count, and status.
- Active chapter uses a quiet blue surface without a darkened left strip.
- Failed/error states use red pill; needs rewrite uses warning pill.

## Center Panel
- Default stage shows original text.
- Summary/scene/rewrite data comes from API outputs.
- Missing AI data must show `暂无数据`, not fake generated text.

## Right Panel
- Current prompt, extracted context, and stage-specific actions.
- One explicit next-stage button where applicable; Enter does not trigger it.
- Error card if API or chapter operations fail.

## Interaction Rules
- Selecting a chapter updates local workspace state and content.
- Export actions call backend endpoints and show generated output path.
- If no project is selected or found, show an `EmptyState` and link to `/library`.
