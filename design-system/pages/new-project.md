# New Project Page

## Purpose
New Project is a sequential, validated flow from project purpose to a ready workspace.

## Layout
- First choose rewrite or extraction.
- Then progress through: 导入文件 / 章节拆分 / 预览信息 / 模型配置 / 提示词策略 / 确认创建.
- Future steps stay unavailable until prerequisites are complete.
- Bottom actions are explicit. Enter never advances the flow.

## Data and Security Rules
- Source file and working directory use Electron system pickers.
- Preview returns metadata and a short-lived preview token.
- Create must submit the preview token, not a fresh unverified path-only request.
- Do not claim browser upload support.

## Empty/Error States
- No file selected: show upload-style placeholder with explicit local path note.
- Unsupported format: show clear supported list TXT / EPUB / DOCX.
- Preview expired: ask user to preview again.

## Visual Notes
- Keep it focused and calm.
- Use the shared blue primary action and neutral paper/canvas surfaces.
