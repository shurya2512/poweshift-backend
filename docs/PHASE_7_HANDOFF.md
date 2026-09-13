# Phase 7 handoff

## Delivered scope

The Network 2 structural scaffold is implemented without starting physical or tactical training.

- The policy schema freezes feature names, manoeuvres, recurrent width and action transform identity.
- The GRU actor/critic applies feature masks and manoeuvre masks and emits a bounded beta deployment
  distribution plus value output.
- Rollout records preserve sampled, issued and delivered actions separately. The sampled joint log
  probability is retained even when delivery is clipped.
- Recurrent steps distinguish true termination from truncation. Termination suppresses bootstrap;
  truncation retains it.
- Checkpoints bind schema, action transform, recurrent shape, physics, rules, fixed pits and scenario.
  Loading uses restricted state-dict deserialization and refuses incompatibility.
- The energy bundle, physical training gate, checkpoint and policy report share one continuous-profile
  identity. A mismatched Phase 4 profile refuses before policy training.
- Route, fixed-pit, ego, replay, encounter, tactical reward and policy admission boundaries fail closed
  when their physical or source evidence is absent.

## Current gate

Only a synthetic structural forward/backward diagnostic has run. Phase 4 profile admission
`87daf272e8ec8f275fae47cade4c71f3c6815c617726b3a9756562ae208871c2` is provisionally promoted.
Physical single-car PPO is still blocked by the missing admitted Phase 5 energy bundle. Two-corner tactical PPO
is additionally blocked by missing admitted interaction evidence, source-supported route continuation
and real fixed-pit context for the selected scenario.

No policy checkpoint has been trained on physical replay. No attack, defence, abort, energy benefit,
tail quality, field behavior, four-corner behavior or strategy advantage is validated.

## Verification

The earlier complete backend suite passed 326 tests. After the profile-integration change, the
20-test Phase 6–7 slice and the 15 directly affected integration checks pass. Python compilation
passes and `git diff --check` is clean. A later complete backend run passed 333 tests after the smoke
completed. Synthetic fixtures cover action masks, likelihood retention, recurrence, checkpoint
compatibility, episode endings, route and pit refusal, encounter persistence and admission reporting.

## Next action

After Phase 4 and Phase 5 admission, freeze the single-car curriculum measure and criteria before
training. Then run the finite recurrent PPO curriculum through the shared environment. Tactical work
starts only after the two-corner interaction world and continuation evidence are admitted. The
fixed-pit preparation and one-update physical PPO preflight are sequenced in `PHASE_8_PLAN.md`.
