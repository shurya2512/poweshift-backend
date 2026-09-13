# Phase 5 handoff

## Delivered scope

The shared powertrain boundary, isolated response comparison, signed energy accounting, historical
rule resolution and readiness reporting are implemented. They are offline and fail closed.

- Power inputs carry requested and delivered shaft values, signed motor DC power, units by field,
  evidence origin, source identity and availability.
- A source allocation replaces effective propulsion at the axle. Nonzero effective throttle and an
  allocation cannot be used together in numerical or differentiable mechanics.
- Source maps refuse unsupported shaft speed and shifts. Finite response is rate-limited. One bounded
  neural residual can represent one named mechanism in a matched comparison.
- Storage energy, recharge throughput and discharge throughput have separate fields. Fuel mass stays
  in mechanics and is updated once at each coupled energy stage.
- Positive terminal power drains storage. Recovery passes through its declared efficiency, store loss
  is named once, and capacity saturation records curtailment.
- Historical rule snapshots bind event, session, UTC interval, source hash, measurement boundary and
  line map. Missing coverage and another event or edition refuse.
- Readiness binds the stable Phase 4 training artifact separately from its later promoted profile.
  Training enables offline experiments; only an admitted profile can enter an energy bundle.
- Energy bundles carry the continuous-profile identity. Physical policy training refuses a different
  profile, and policy checkpoints and admission reports retain the same identity.

## Current gate

Offline Phase 5 work is enabled against the stable Phase 4 interface and the v8 source-bound training
artifact. The provisional Phase 4 profile admission is
`87daf272e8ec8f275fae47cade4c71f3c6815c617726b3a9756562ae208871c2`. Runtime is disabled. The
checkout has no frozen real response evidence, accounting evidence or complete historical rule inventory. Synthetic tests
establish contract behavior only. They do not validate a physical power split, storage capacity,
response model, rule value or vehicle ranking.

The next valid action is to freeze each real evidence set and its acceptance criteria, then run the
matched offline response, accounting and rule experiments. The Phase 4 diagnostic smoke is complete. Joint
bundle admission waits for those results and numerical and differentiable compatibility; the promoted
provisional profile identity is available for that binding.

## Verification

The earlier complete backend suite passed 326 tests. After the profile-integration change, the
22-test Phase 5 slice and the 15 directly affected integration checks pass. Python compilation passes
and `git diff --check` is clean. A later complete backend run passed 333 tests after the smoke
completed. The existing Torch `searchsorted` non-contiguous-input performance warning is unrelated.

## Context7 fallback

Context7 was unavailable. Established repository patterns were used for NumPy and PyTorch, and the
official PyTorch documentation was checked for GRU, distributions, optimizer and restricted
checkpoint loading behavior. No framework behavior was inferred to admit runtime physics.
