# Rusty Text Workbench Design System

> Status: UI baseline locked on 2026-07-23. New screens must reuse the tokens and component families below. The executable source of truth is `desktop/src/styles/theme.css`; this document records intent and constraints.

## 1. Product position

Rusty is a desktop long-form text workbench, not a dashboard. The interface must keep chapter structure, manuscript text, project-derived material, and the next workflow action visible without turning every region into a decorative card.

Primary reference: Scrivener's Binder / Editor / Inspector information architecture. Rusty keeps an original visual identity and implements only the structures that serve its two workflows.

Concept sources:

- `concepts/rusty-new-project-v1.png`
- `concepts/rusty-rewrite-workspace-v1.png`
- `concepts/rusty-extraction-workspace-v1.png`
- `concepts/rusty-prompt-management-v1.png`

## 2. Core layout

### App shell

- Native window/title region: 30px.
- Primary app rail: 72px desktop; every entry is a 56px icon-plus-label button.
- The light/dark switch is the last rail entry at bottom-left and uses the same dimensions, icon size, type scale, hover state, and horizontal alignment as the five route entries.
- Route content fills remaining width and height. The engineering library may keep a restrained maximum width; prompts, outlines, characters, models, setup, and project workspaces do not add decorative outer whitespace.
- Status/action bars remain visible while their own content regions scroll.

### Project workbench

- Chapter Binder: default 240px; minimum 196px; collapsible below 1280px.
- Center Editor: always the dominant flexible region; minimum 520px on desktop.
- Inspector: default 300px; minimum 260px; collapsible below 1280px.
- Dividers use an 8px interaction target with a 1px visible rule.
- Each panel owns its vertical scrolling. Avoid whole-page scroll traps.

### Prompt management

- Template library: 244px.
- Main editor: flexible, minimum 560px.
- Stable bottom save bar: 64px.

## 3. Color tokens

```css
:root {
  --canvas: #f2f4f7;
  --chrome: #f2f4f7;
  --paper: #ffffff;
  --paper-muted: #f2f4f7;
  --border: #e0e6ee;
  --border-strong: #d2dbe7;
  --ink: #19202c;
  --ink-muted: #5f6978;
  --ink-soft: #8a94a3;
  --accent: #2458d8;
  --accent-hover: #1d49b9;
  --accent-soft: #edf3ff;
  --success: #23814b;
  --warning: #c66a13;
  --danger: #c93636;
  --focus: #3f75f0;
}

:root[data-theme="dark"] {
  --canvas: #15181d;
  --chrome: #181b21;
  --paper: #20242b;
  --paper-muted: #292e36;
  --border: #353c46;
  --border-strong: #46505d;
  --ink: #edf1f7;
  --ink-muted: #abb4c1;
  --ink-soft: #7f8997;
  --accent: #6f96ff;
  --accent-hover: #89a8ff;
  --accent-soft: #263b66;
}
```

Rules:

- In light mode, paper surfaces are true white, not cream. In dark mode, use neutral blue-black layers rather than pure black.
- No ambient gradient, glass blur, neon glow, or colored shadow.
- Accent blue marks selection and the primary next action only.
- Green/orange/red are semantic states, never decoration.
- Components consume semantic tokens; page-level hard-coded light or dark colors are not allowed.
- Theme selection is persisted under the versioned key `rusty.ui.theme.v1` and defaults to the operating-system preference on first use.

## 4. Typography

UI stack:

```css
font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", system-ui, sans-serif;
```

Manuscript stack:

```css
font-family: "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", SimSun, serif;
```

Scale:

- Route title: 24-30px / 650.
- Project/chapter title: 20px / 650.
- Panel title: 16px / 650.
- Section title: 14px / 650.
- UI body and controls: 14px / 400-600.
- Metadata: 12px / 400-550.
- Manuscript: 16px / 400 / 1.8.
- Prompt and structured analysis editor: 14px / 400 / 1.65.

Do not shrink Chinese labels to fit. Truncate list-row titles only when the full value remains available through title/accessible text.

## 5. Spacing and geometry

- 4px base spacing system.
- Dense toolbars: 8px gaps.
- Panel padding: 12-16px.
- Editor page padding: 24-32px desktop, 16-20px narrow.
- Small control radius: 6px.
- Button/input radius: 8px.
- Panel/section radius: 10-12px only when a contained group is needed.
- Shadows: none for normal panels; one subtle `0 2px 8px rgb(20 30 50 / 8%)` for overlays only.

## 6. Controls

- Common buttons: minimum 36px tall; primary workflow actions: 40-44px.
- Icon-only controls: 36x36px with tooltip and accessible name.
- Inputs/selects: 40px tall by default.
- Textareas have visible labels, comfortable internal padding, and resizable or panel-filling behavior appropriate to context.
- Focus ring: 2px accent outline with 2px offset.
- Primary button: solid accent blue, white text.
- Secondary: white or chrome surface, border, ink text.
- Ghost: transparent, used only in toolbars.
- Danger: red text/border; solid red only in confirmation dialog.

Avoid tiny pills. Status uses a colored dot plus short text in dense chapter lists; use compact labels only where a dot is insufficient.

## 7. Component families

- `AppRail`: route navigation with selected rail indicator.
- `ChapterBinder`: project heading, progress, chapter rows, stage status, collapse control.
- `WorkbenchToolbar`: current chapter, previous/next, panel visibility, current prompt.
- `WorkflowRail`: 40px stage tabs with completed/current/available states.
- `ManuscriptPane`: header, word count, true-white scrolling text/editor surface.
- `Inspector`: context tabs and project/chapter actions.
- `StatusBar`: chapter position, words, save/generation status.
- `TemplateLibrary`: search, create/import, selectable template rows.
- `PromptEditor`: rewrite/analysis mode tabs plus mode-specific editor.
- `ActionBar`: stable save/create/export actions; never floating over text.

## 8. Workflow-specific layouts

### Rewrite project

- Stages: 原文 / 剧情与人物 / 目标骨架 / 改写对照 / 导出检查.
- Comparison stage uses two equal panes on wide screens.
- Inspector exposes skeleton, related characters, and generation provenance.
- Generated text remains editable; accept/confirm is explicit.

### Extraction project

- Stages: 原文 / 章节风格分析 / 人工审查 / 全书归纳 / 提示词预览 / 导出 JSON.
- Review stage uses source evidence beside editable structured analysis.
- Inspector exposes the selected analysis prompt and evidence completeness.
- Never display story anchors or character cards as extraction output.

### New project

- Three visible setup regions: project type, file/preview, prompt/settings.
- At 1280x720, content can scroll but the create/cancel action bar stays visible.
- Rewrite chooses a rewrite prompt; extraction chooses an analysis prompt.

### Prompt management

- Top modes: 改写提示词 / 分析提示词.
- Rewrite tabs: 基础规则 / 识别规则 / 改写规则.
- Analysis tabs: 分析维度 / 证据规则 / 归纳输出.
- Story and character anchors never appear as rewrite-template tabs.

## 9. Responsive rules

- `>= 1360px`: full Binder + Editor + Inspector.
- `1100-1359px`: one auxiliary panel may collapse; center remains usable.
- `800-1099px`: Binder becomes a drawer; Inspector becomes a drawer; comparison panes can remain split if each is at least 360px, otherwise stack.
- `< 800px`: single active work panel, drawer navigation, sticky stage/action bars, no horizontal page overflow.

Acceptance viewports: 1440x900, 1280x720, and one narrower browser viewport.

## 10. Accessibility and state

- Visible `:focus-visible` on every interactive element.
- Controls have labels or `aria-label`; icon meaning is never color-only.
- Loading is local to the affected action/panel.
- Empty/error states explain the next action without replacing the entire shell.
- Long generation errors preserve an optional technical detail section.
- Respect `prefers-reduced-motion`; transitions are 120-180ms and functional.

## 11. Forbidden patterns

- Glassmorphism, ambient gradients, oversized rounded cards, bento dashboards.
- Floating action docks that cover manuscript text.
- Fixed panel widths with no collapse or narrow-screen strategy.
- Buttons below 36px for frequent actions.
- Story/person anchors inside reusable rewrite prompt templates.
- Whole-page scrolling when a Binder, editor, or Inspector should scroll independently.
- Decorative metrics, fake data, illustrations, or marketing copy in the workbench.
