# Home Page

## Purpose
Home is the personal dashboard and emotional entry point. It should establish Rusty as a local writing studio and show real project state from the backend.

## Layout
- Top center hero with current time, date, and the line `Build in public, write in private.`
- Tag row: 策划 / 脚本 / 改写 / 发布.
- Metric row: 本月改写章节, 作品库项目数, 草稿数, 待处理章节数.
- Middle grid: profile/studio card, navigation command card, progress card.
- Lower grid: pending chapters or empty state, trend/statistics card.

## Components
- `MetricCard` for dashboard numbers.
- `GlassCard` for profile, navigation, progress, and trend blocks.
- `EmptyState` when no projects exist.
- `StatusPill` for project states.

## Data Rules
- Use backend project list for project count and progress summary.
- If no project exists, show a clear empty state and route to `/new-project`.
- Do not hardcode creator names or external publishing platforms.

## Visual Notes
- This page gets the richest ambient background.
- Large clock can use gold highlight.
- Navigation cards should feel like command tiles, not admin shortcuts.
