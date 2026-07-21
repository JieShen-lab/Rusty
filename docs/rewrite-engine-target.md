# Rusty rewrite engine target

Rusty compiles project assets into explicit AI requests and applies structured
results deterministically.

## Runtime layers

1. **Assets**: rewrite template, style template, outline, character cards,
   chapter summary, scene markers, project targets, and chapter text.
2. **Compiler**: Rusty-native rules plus user assets become a versioned list of
   model messages and an output contract.
3. **Executor**: sends the compiled request and records every attempt.
4. **Validator**: classifies provider, refusal, JSON, anchor, and length errors.
5. **Applier**: replaces an exact anchor or accepts a full rewrite, then stores
   the resulting chapter for review.

## Rewrite modes

- `anchor_expand` is the default. The model returns `anchor` and `expanded` as
  JSON. Rusty requires a non-empty anchor that occurs exactly once.
- `full_rewrite` remains available for tasks that intentionally replace the
  complete chapter.

## Traceability contract

Every attempt stores the actual messages sent, model/template identifiers,
response text, parsed output or classified error, token usage, and elapsed
time. A saved prompt snapshot is the same compiled object that was sent; it is
never reconstructed after the request.

## Compatibility policy

Legacy FleshOut-shaped JSON may be imported as compatibility data. Fields that
do not map to a documented Rusty concept remain metadata until the user
explicitly reviews and promotes them. Importing a file never silently enables
an opaque rule.

