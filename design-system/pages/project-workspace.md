# Project Workspace Page

## Purpose
The workspace is the core writing and rewrite command center for one project. It must be project-bound through `/workspace/:projectId` and recover on refresh.

## Layout
- Header: project name, status pill, update metadata.
- Stage stepper: 书籍拆分, 内容总结, 识别待处理, AI 改写, 合并输出.
- Three-column body on desktop:
  - Left: chapter navigation.
  - Center: chapter content and AI output.
  - Right: stats, progress, exports, errors.

## Chapter Navigation
- Show title, word count, and status.
- Active chapter uses blue/cyan border glow.
- Failed/error states use red pill; needs rewrite uses warning pill.

## Center Panel
- Default stage shows original text.
- Summary/scene/rewrite data comes from API outputs.
- Missing AI data must show `暂无数据`, not fake generated text.

## Right Panel
- Project metrics.
- Export TXT/EPUB buttons.
- Error card if API or chapter errors exist.

## Interaction Rules
- Selecting a chapter updates the URL-local state and content.
- Export actions call backend endpoints and show generated output path.
- If no project is selected or found, show an `EmptyState` and link to `/library`.
