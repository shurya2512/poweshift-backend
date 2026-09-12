# Poweshift Backend Ground Rules

## Purpose and evidence

- Rebuild the backend from scratch here, using cached data copied from sibling `track-shift`.
- Preserve the source data. Migrate the approved FastF1 cache before Phase 1; inventory, provenance, and integrity checks belong to the first phase.
- Deliver a defensible real-data MVP within a short timeframe. Bound every claim to measured evidence.
- Clearly label simulated and inferred outputs. Passing tests are not scientific validation.

## Phase process

- Each phase starts with a plain-language specification of at most 400 lines, written with `writing-specs`.
- The specification states acceptance criteria, tests, and a plan for roughly three or four commits. Pull requests are not the required unit of scope here.
- A human must approve the specification before implementation begins.
- The main session only orchestrates; it does not author phase artefacts.
- Stop after every phase. The phase-end handoff takes precedence over moving to the next phase; a human carries its context forward.
- Before retiring a phase specification, move durable content into permanent documentation.

## Roles and verification

- Terra writes specifications, code, test suites, documentation, and handoffs. Use `gpt-5.6-terra` on ChatGPT, otherwise Sonnet.
- Luna runs the suite and reports the evidence. Use `gpt-5.6-luna` on ChatGPT, otherwise Haiku. The role measures and reports rather than judges.
- Use Sol only when test or acceptance evidence shows an unmet requirement: `gpt-5.6-sol` with high reasoning on ChatGPT, otherwise Opus. The role is judgement. Terra fixes it, then Luna reruns the relevant tests.
- A passing phase does not require a Sol review. When a workflow is used, record these model assignments in `meta.phases`.

## Change discipline

- Apply `code-etiquette`, except that required specifications, handoffs, and project instructions may be new documents and work is planned as commits rather than PRs.
- Keep decisions, pending choices, and deviations with their reasons synchronized with the code in the same change.
- Preserve user files and existing edits. Do not delete, move, discard, or overwrite them without explicit approval.
- Do not add a `Co-Authored-By` trailer to commits.
- Prioritize a working implementation. Keep testing and review proportional: use a small set of meaningful checks, avoid repeated review rounds and unnecessary polish, and accept simple, rough code when it meets the requested behavior.

## Routine commands

- Routine commands within an approved phase are authorized without further conversation.
- Sandbox approval remains required where the environment enforces it.

## Code-producing briefs

- Require Context7 before edits: resolve the library, then query exact signatures and behavioral semantics for every framework, API, library, SDK, CLI, or third-party module used.
- If Context7 is unavailable, use official documentation or existing project usage and state the uncertainty.
- Comments, docstrings, and function descriptions are one or two short plain-language lines. Do not use spec IDs, history, or measurement logs.

## Phase-end handoff

- Terra records delivered scope, commits, checks and results, limitations, changed decisions, pending decisions, and the context needed next.
