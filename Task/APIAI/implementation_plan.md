# Implementation Plan: zh-CN Validator, Glossary, and Subtitle Rewrite

## Goal

Recover final subtitle quality for zh-CN → vi-VN runs by keeping the
contextual translation path alive, reducing false-positive QA failures,
enforcing glossary terms, and rewriting fragmented subtitle groups before
render.

## Workstreams

### 1. Validator refactor

- Make validation language-aware by accepting `source_language`.
- Split broad hallucination logic into:
  - `LENGTH_RATIO_WARNING`
  - `READABILITY_WARNING`
  - `TRUE_HALLUCINATION`
- Keep subtitle-only timing/length pressure as warnings unless truly unsafe.
- Add glossary-driven checks:
  - `GLOSSARY_MISMATCH`
  - `BANNED_WRONG_TERM`
- Add subtitle fragmentation detection:
  - `FRAGMENTED_SUBTITLE`

### 2. Repair loop policy

- Only send critical issue types to AI repair.
- Skip repair for soft warnings such as length ratio and soft timing.
- Stop retrying when repair does not reduce bad-segment count or does not
  materially change the targeted text.

### 3. Final transcript selection policy

- Preserve contextual translation whenever only warnings remain.
- Only fall back when critical issues remain after repair.
- If fallback is used, it must still pass through glossary enforcement,
  validation, and subtitle-group rewrite before becoming final output.

### 4. Glossary enforcement

- Create `src/glossary_enforcer.py`.
- Normalize noisy ASR/source variants before enforcing glossary.
- Apply glossary enforcement:
  1. after contextual translation
  2. after repair
  3. after fallback

### 5. Subtitle group rewrite

- Create `src/subtitle_group_rewriter.py`.
- Detect lead-in / continuation segments that form one natural phrase across
  2–4 subtitle segments.
- Rewrite grouped subtitle text without changing timing in v1.
- Focus first on subtitle-only mode.

### 6. Tests

- Add validator tests for zh-CN compact-source valid translations.
- Add pipeline tests proving warning-only outputs do not trigger fallback.
- Add glossary enforcement tests for required terms like `thuyền bay`.
- Add subtitle-group rewrite tests for fragmented segment pairs.
