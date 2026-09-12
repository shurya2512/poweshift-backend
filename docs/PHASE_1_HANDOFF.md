# Phase 1 handoff

## Delivered evidence

The final bundle is `data/acquisition_verified_d22e9c4/acquisition_bundle.json`. It contains six Bahrain preseason identities: 11, 12, 13, 18, 19 and 20 February 2026. FastF1 3.8.3 supplied eight separately exported streams for every day: car, position, laps, tyres, weather, session status, track status and race-control messages.

Each stream export has a hash, native source-row key, parser-derived provenance and a sealed parser-cache snapshot hash. Each day has a hashable FastF1 loader log. The source cache remains separate and unchanged; the final cache and evidence roots are ignored generated data.

## Coverage result

All eight streams are present for all six days. The session roster is 22 entries on every day. Critical-stream exclusions are 4, 7, 5, 1, 6 and 6 entries respectively for 11, 12, 13, 18, 19 and 20 February. Those are source-coverage exclusions, not performance findings.

The bundle keeps `downstream_ready=false`. The proposed split is recorded but inactive: Test 1 for training, 18 February for selection, and 19-20 February for final evaluation. A human coverage review must decide whether the exclusions block all later work or exclude individual entries.

## Checks and commands

`uv run pytest` passed 24 tests before final evidence generation. The final evidence was generated with:

```sh
uv run python -m poweshift_backend \
  --cache-dir data/phase1_fastf1_cache \
  --output-dir data/acquisition_verified_d22e9c4
```

The command reused the dedicated local cache and did not read or modify `data/fastf1data`.

## Limits and decisions

This phase establishes source availability and traceability only. It does not establish car performance, rank fidelity, energy accuracy, usable model targets, or a supported split. FastF1 parser corrections and availability warnings are retained in each loader log; exports are explicitly parser-derived rather than raw observations.

Fourteen commits were needed instead of the planned four because reviewer-found provenance, immutable-capture and stream-status issues required bounded corrections. An incomplete ignored recapture root with 55 files was removed before a corrected recapture; it is recoverable from the unchanged dedicated FastF1 cache. Later recap roots were preserved.

## Next decision

Approve or reject the coverage review before any preparation, performance inspection, split activation or Phase 2 work. The approved Phase 1 specification remains until final acceptance and durable-content transfer are confirmed.
