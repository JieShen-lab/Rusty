# FleshOut reference boundary

This document records observable behavior from the locally supplied FleshOut
0.2.0 executable. It is a compatibility reference, not a source of Rusty
product rules or copied prompt text.

## Evidence labels

- **Confirmed**: visible in the executable, its SQLite schema, or its logs.
- **Inferred**: strongly suggested by those artifacts but not yet verified by
  a captured request.
- **Unknown**: requires a controlled run against a local mock API.

## Confirmed behavior

- The application is a Tauri desktop application with a Rust backend.
- Prompt templates have separate summary, identification, rewrite, and legacy
  auxiliary/breakthrough fields.
- The automated workflow has distinct summary, identification, rewrite, and
  merge stages.
- Identification produces categories and contextual descriptions that are fed
  into rewriting.
- Rewrite prompts include a fixed application scaffold in addition to imported
  template text and dynamic chapter material.
- The rewrite path requests structured anchor/expanded output, validates it,
  and merges the expanded fragment into the original chapter.
- Logs show incremental expansion, anchor matching, parse failures, retries,
  per-stage status, and project-level concurrency.
- A diagnostic export format contains the final system and user prompts.
- The executable contains refusal/parse detection strings. This proves output
  classification exists; it does not prove that any particular hidden prompt
  bypasses provider policy.

## Inferred behavior

- Imported auxiliary/breakthrough text is probably added to one of the rewrite
  messages. Exact role and ordering still require request capture.
- A rewrite request appears to choose one primary anchor even when several
  identification markers are available.
- Stage reruns appear to invalidate some downstream results.

## Rusty rule boundary

Rusty may adopt the architectural ideas above: explicit prompt compilation,
stage isolation, structured contracts, deterministic patching, retries, and
traceability. Rusty must not silently copy FleshOut prompt wording or treat a
FleshOut compatibility field as a Rusty-native instruction.

Rusty-native rules must therefore be:

1. written independently for Rusty;
2. visible in source and in the compiled-request preview;
3. versioned with a stable ruleset identifier;
4. separable from user templates and imported compatibility metadata;
5. subject to the configured model provider's policies.

