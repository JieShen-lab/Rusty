# Document Workbench Design QA

- Primary source visual truth: `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-c6ab6ada-8845-4ff2-b4a5-f3a5f1242aef.png`
- Focused references:
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-fecff2ee-db1b-41bf-b6ad-85ceb493add5.png`
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-6238674b-7742-4dba-9b45-1b08e16222be.png`
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-0d3bccb8-dab3-43e5-84e4-0898562d57fc.png`
- Implementation screenshot: `C:\Users\yuye2\.codex\visualizations\2026\07\25\019f98f8-54e4-7be3-a09e-a5d40d68066f\document-workbench-shared-ui.png`
- Combined comparison: `C:\Users\yuye2\.codex\visualizations\2026\07\25\019f98f8-54e4-7be3-a09e-a5d40d68066f\document-project-ui-comparison.png`
- Browser viewport: 1600 × 900 CSS px, desktop, light theme.

## Full-view comparison

The document workbench now directly reuses the project workbench structure and visual classes:

- project-style toolbar and centered title metadata;
- separately bordered and rounded chapter, manuscript, and inspector cards;
- shared chapter binder header, rows, selection state, and scroll footer;
- shared manuscript pane header, serif body typography, width, line height, and spacing;
- shared inspector card and action-row treatment.

## Requested removals

- The “整本文档” directory row is absent.
- The “拖动章节可调整顺序” helper copy is absent.
- The inspector information contains only title, author, total word count, and chapter count.
- Format, import date, storage path, and status details are absent from the entered-document inspector.

## Interaction and rendering evidence

- Double-clicking the bookshelf item opened the document workbench.
- The first detected chapter was selected and loaded by default.
- Two chapter rows rendered and remained draggable.
- The center manuscript reports the selected chapter's word count.
- Six document-processing actions and the export action remain visible.
- Shared manuscript computed styles: `font-size: 16px`, `line-height: 32px`, `max-width: 760px`.
- No application-origin console errors were observed. Two Edge Translate extension warnings were excluded as browser-extension noise.

## Findings

No actionable P0, P1, or P2 differences remain for the requested shared project styling, directory simplification, or inspector reduction.

final result: passed

---

# Library Browser Annotation QA — Round 2

- Source references:
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-2276eb2b-8667-4bdd-93e1-4828d3a640bf.png`
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-ca17a911-263d-42cc-bd1b-5e348508e6d4.png`
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-c35c5744-2a09-4780-82a4-08a4fe3f212e.png`
- Final renders:
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\documents-library-round2.png`
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\characters-library-round2.png`
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\materials-library-round2.png`
- Side-by-side comparisons:
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\documents-library-round2-comparison.png`
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\characters-library-round2-comparison.png`
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\materials-library-round2-comparison.png`
- Browser viewport: 1720 × 900 CSS px, desktop, light theme.

## Verified changes

- Library and model feedback banners use the same restrained success/error treatment and automatically dismiss.
- Document title and author are click-to-edit fields backed by a persistent API; saved values refresh both detail content and the book cover.
- File size moved into the metadata list, category controls are checkbox-free pills, the “可多选” hint and “文档目录” heading were removed.
- Document, character, and material inspector actions share one two-column outlined-button standard.
- Material subcategories now use document-library row anatomy, counts, an operational uncategorized filter, and a separate “我的分类” group.
- Character role filters retain their domain-specific meaning while matching the document-library navigation anatomy and counts.

## Findings

No actionable P0, P1, or P2 differences remain for the requested annotations.

final result: passed

---

# Library Browser Annotation QA

- Source references:
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-a5ec9ab3-8ddd-4911-a2f6-fcb1252f6929.png`
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-6b480dad-1170-4b0d-9c1e-02bd80e079fc.png`
  - `C:\Users\yuye2\AppData\Local\Temp\codex-clipboard-1de26bb9-7b67-4984-b54f-3c598855bf34.png`
- Implementation screenshots:
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\documents-library-final.png`
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\materials-library-final.png`
  - `C:\Users\yuye2\.codex\visualizations\2026\07\26\019f9c56-46ac-72c0-8078-6cd3a7f7f09e\characters-library-final.png`
- Browser viewport: 1720 × 900 CSS px, desktop, light theme.

## Verified changes

- Document cards retain their book covers; the cover brand label was removed.
- Document search and detail headings align to the annotated positions, redundant counts/status/menus were removed, and detail typography was enlarged.
- The document “工程分类” shortcut is positioned between “收藏” and “最近导入” and is excluded from user-managed categories.
- Material scope switching occupies the former category-header position; the search is left aligned and public material categories follow the document-library hierarchy.
- Character scope and role subdivisions follow the same left-navigation pattern, card editing opens on double click, and the main card surface has no cover artwork.
- Material and character AI extraction/import entry points remain visible.

## Findings

No actionable P0, P1, or P2 visual differences remain for the requested annotated changes.

final result: passed
