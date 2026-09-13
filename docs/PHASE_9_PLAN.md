# Phase 9 Chronological News and Adaptation Plan

## Feature request brief

The backend can update an entry profile from completed telemetry, but it has no durable way to
record when technical news became knowable, whether it applies to an entry, or whether it helped.
Without that boundary, later-weekend learning can leak future information or turn a headline into
an invented performance gain.

Phase 9 adds a source-attributed news record and a chronological update record. News remains zero
numerical influence until a later matched comparison proves benefit. Validation and final-test
weekends remain score-only evidence and cannot update the model that is being measured.

## Delivery status

The minimal contract and service boundary is implemented and covered by seven focused tests. No
article has been admitted and no positive numerical news effect is claimed; an authorised completed
training stint and later matched comparison are still required before promotion.

## Functional requirements

- Capture article identity, source, publication time, first-known time, content hash and visible text.
- Require a reviewed source span, entry fitment and component claim before creating news context.
- Reject news that was not available by the completed-stint cutoff.
- Keep news influence at zero until a frozen telemetry-only comparison is beaten.
- Build one immutable update manifest from an active profile and a completed authorised stint.
- Permit profile updates only from the training partition.
- Keep validation, final evaluation and reserved evidence read-only.
- Record promote, retain or refuse decisions with the evidence identities that caused them.

## Non-functional requirements

- News fetching runs outside inference with bounded HTTPS requests and response size.
- Every saved artifact is strict, canonically hashed and refuses incompatible replacement.
- No route accepts a URL, executable object or filesystem path from an API client.
- Passing tests establish contract behavior, not a beneficial news effect.

## Scope

### In

- Registered article capture, review and bounded news context.
- Completed-stint chronology and profile-update manifests.
- Matched news-versus-telemetry-only promotion records.

### Deferred

- Automated extraction beyond conservative visible-text capture.
- Shared-weight retraining, which still waits for authorised completed weekends.
- A positive numerical news effect, which still needs measured ablation evidence.

| Not doing | Why |
|---|---|
| Turning headlines into power changes | No measured causal mapping exists. |
| Updating from protected weekends | It would invalidate the evaluation. |
| Fetching news inside inference | Network delay and later edits would break reproducibility. |

## Process flow

```mermaid
flowchart LR
    A["Registered article"] --> B["Bounded capture"]
    B --> C["Human review and fitment"]
    C --> D["Zero-influence news context"]
    E["Completed training stint"] --> F["Chronological update manifest"]
    D --> F
    F --> G["Candidate profile"]
    G --> H["Matched later comparison"]
    H --> I["Promote, retain or refuse"]
    classDef source fill:#1d4ed8,color:#ffffff,stroke:#1e3a8a
    classDef process fill:#0f766e,color:#ffffff,stroke:#134e4a
    classDef gate fill:#b45309,color:#ffffff,stroke:#78350f
    class A,E source
    class B,C,D,F,G process
    class H,I gate
```

## Exact planned changes

| Area | Change |
|---|---|
| News contracts and services | Add strict article, review and news-context artifacts. |
| Learning records | Add chronological update and promotion records. |
| Tests | Check time leakage, partition refusal, stable hashes and zero default influence. |
| Permanent docs | Record the delivered boundary and remaining evidence gap. |

Blast radius: two new package families, contract exports, focused tests and existing architecture.

## Testing cases

| Test group | Why it matters |
|---|---|
| Article capture and review | Prevents unattributed or changed text from entering learning. |
| Availability cutoff | Prevents future news from changing an earlier profile. |
| Partition firewall | Keeps validation and final-test evidence untouched. |
| Promotion evidence | Prevents an unmeasured headline from becoming a numeric gain. |
