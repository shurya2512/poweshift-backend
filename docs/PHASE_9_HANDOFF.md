# Phase 9 handoff

## Delivered scope

- HTTPS-only article sources carry publication and first-known times with explicit time zones.
- Capture hashes the exact response bytes, bounds the streamed response and extracts visible text.
- Human review binds an entry, component, claim type, exact source span, fitment status and review time.
- News context refuses unavailable or unreviewed evidence and starts with zero numerical influence.
- Profile-update manifests accept completed training evidence only and bind model, transform, parent
  profile, source run, source hash, cutoff and news context IDs.
- Promotion records give news numerical influence only when a matched news metric is strictly better
  than its telemetry-only counterpart.

## Verification

The focused Phase 9 test file passes 7 tests. It covers capture identity, absolute chronology,
unavailable evidence, zero influence, the protected-partition firewall and matched promotion. The
complete backend suite passes 421 tests with one unrelated performance warning.

## Remaining gate

No article has been admitted and no positive effect has been measured. The actual encoder update,
candidate profile rebuild and later real-weekend comparison still need completed authorised training
evidence. Validation and final-evaluation weekends cannot update the profile being measured.

## Next action

After an authorised training stint completes, register its immutable source and any reviewed news
available by that cutoff. Build the update manifest, run the existing quality-gated representation
update, then compare the candidate against the telemetry-only path on a later matched holdout.
