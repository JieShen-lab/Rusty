# Models Page

## Purpose
UI-R2 Models is an entry point into AI model configuration. In this round it may be list-only or clearly marked as a placeholder, but must not expose API keys.

## Layout
- Header: 模型.
- Left/list area: model cards with display name, provider, model name, default marker, API key presence.
- Right/detail area: selected model read-only details or `UI-R2 暂不编辑` message.

## Data Rules
- Prefer list-only API from `ModelService.list_models()`.
- Never return or render real API keys.
- If write APIs are not implemented, disable edit/save controls and label them as UI-R3 work.

## Visual Notes
- Use technical blue/cyan accents.
- Use success pill only for default/ready states.
