# Models Page

## Purpose
Models manages the AI connections used by project creation and generation.

## Layout
- Header: 模型.
- Left/list area: model cards with display name, provider, model name, default marker, API key presence.
- Right/detail area: create/edit form, default-model option, connection test, save, and delete.

## Data Rules
- API keys are write-only in responses and stored through the backend keyring.
- An unchanged masked key must never overwrite the stored secret.
- Connection status, default status, and saved-key status use semantic theme tokens.

## Visual Notes
- Use the shared blue accent only for selection and primary actions.
- Use success pill only for default/ready states.
