# New Project Page

## Purpose
UI-R2 New Project is a minimal closed loop: selected local file path -> preview -> create -> project appears in library/workspace. It is not the old six-step wizard.

## Layout
- Left glass panel: local file/workspace path inputs, guidance, and safety note.
- Right preview panel: parsed metadata, chapter count, word count, first chapters.
- Bottom action strip: 预览, 创建工程, 返回作品库.

## Data and Security Rules
- In UI-R2, path entry is local-development mode unless Electron IPC file picker is wired.
- Preview returns metadata and a short-lived preview token.
- Create must submit the preview token, not a fresh unverified path-only request.
- Do not claim browser upload support.

## Empty/Error States
- No file selected: show upload-style placeholder with explicit local path note.
- Unsupported format: show clear supported list TXT / EPUB / DOCX.
- Preview expired: ask user to preview again.

## Visual Notes
- Keep it focused and calm.
- Use gold for the create action and blue for preview.
