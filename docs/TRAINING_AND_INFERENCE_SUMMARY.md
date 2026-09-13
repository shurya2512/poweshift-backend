# Power-Shift Training and Inference Summary

## What problem this system addresses

Power-Shift must decide when electrical energy is worth spending, when it should be recovered, and
whether the car should attack, defend or hold. Those decisions depend on the fitted car, current
traffic, remaining race horizon and finite battery state. The implementation makes those choices
auditable without pretending that provisional physics are already validated.

```mermaid
flowchart LR
    Problem["Finite energy across a lap or race"] --> NeedA["Choose deployment timing"]
    Problem --> NeedB["Choose harvesting timing"]
    Traffic["Changing gaps and closing speeds"] --> NeedC["Recognise attack windows"]
    Traffic --> NeedD["Recognise defence threats"]
    Identity["Different fitted car profiles"] --> NeedE["Keep policy behaviour profile-specific"]
    Horizon["Qualifying lap or long race"] --> NeedF["Value energy differently over time"]

    NeedA --> Policy["Recurrent hybrid policy"]
    NeedB --> Policy
    NeedC --> Policy
    NeedD --> Policy
    NeedE --> Policy
    NeedF --> Policy

    Policy --> Discrete["HOLD / ATTACK / DEFEND"]
    Policy --> Continuous["Requested electrical fraction"]
    Discrete --> Allocator["Energy and action guard"]
    Continuous --> Allocator
    Allocator --> Delivered["Reachable wheel power"]
    Allocator --> Ledger["Deployment, harvest and battery ledger"]
    Delivered --> Report["Lap and decision reports"]
    Ledger --> Report
```

## Evidence and assumption boundary

The current policies are diagnostic. They use a diagnosed percentage assumption rather than the
earlier fixed-power example: electrical wheel power may add up to 20% of the fitted ICE wheel-power
capability. The usable store and fallback per-lap harvest cap are both 5 MJ. Motor and harvesting
efficiencies are 0.95 and 0.8. These assumptions condition the results; they are not measured battery
or power-unit identification.

```mermaid
flowchart TB
    subgraph Measured["Source-bound measured evidence"]
        Car["Car telemetry"]
        Laps["Lap timing and status"]
        Position["Position telemetry"]
        Control["Track and race-control status"]
    end

    subgraph Diagnosed["Declared diagnostic assumptions"]
        Boost["20% additive electric wheel-power fraction"]
        Store["5 MJ usable store"]
        Harvest["5 MJ/lap fallback harvest cap"]
        Efficiency["0.95 motor / 0.8 harvest efficiency"]
        EgoControl["Causal ego speed-demand controller"]
    end

    subgraph Learned["Learned state"]
        Profile["One fitted profile per entry"]
        Actor["Recurrent actor"]
        Critic["Recurrent critic"]
        Optimizer["Retained optimizer state"]
    end

    Measured --> Training["Diagnostic training"]
    Diagnosed --> Training
    Learned --> Training
    Training --> Checkpoint["Restricted state-dict checkpoint"]
    Checkpoint --> Evaluation["Protected or withheld evaluation"]
    Evaluation --> Label["physics_admission = false"]
```

## How training works

Each promoted car profile owns its own policy and optimizer. Sessions run chronologically. Model and
optimizer weights cross session boundaries; recurrent memory and battery state reset at each new
session. Within a session, long-horizon recurrent and energy state continue across laps.

```mermaid
flowchart LR
    Japan["Japan profile checkpoint"] --> MiamiP["Miami practice"]
    MiamiP --> MiamiR["Miami race"]
    MiamiR --> CanadaP["Canada practice"]
    CanadaP --> CanadaR["Canada race"]
    CanadaR --> MonacoP["Monaco practice"]
    MonacoP --> MonacoR["Monaco race"]
    MonacoR --> BarcelonaP["Barcelona practice"]
    BarcelonaP --> BarcelonaR["Barcelona race"]
    BarcelonaR --> AustriaP["Austria practice"]
    AustriaP --> AustriaR["Austria race"]
    AustriaR --> BritainP["Britain practice"]
    BritainP --> BritainR["Britain race"]
    BritainR --> Final["Final per-profile checkpoints"]

    classDef practice fill:#1d4ed8,color:#fff,stroke:#1e3a8a
    classDef race fill:#b45309,color:#fff,stroke:#78350f
    class MiamiP,CanadaP,MonacoP,BarcelonaP,AustriaP,BritainP practice
    class MiamiR,CanadaR,MonacoR,BarcelonaR,AustriaR,BritainR race
```

```mermaid
flowchart TB
    Session["Start session"] --> Reset["Reset battery and recurrent memory"]
    Reset --> Kind{"Session kind"}
    Kind -->|Practice| PracticeMask["Mask tactics to HOLD"]
    PracticeMask --> EnergyOnly["Learn deployment and harvesting"]
    Kind -->|Race| Split["Chronological 80 / 20 lap split"]
    Split --> Train["Earlier 80% updates policy"]
    Split --> Holdout["Final 20% remains untouched"]
    Train --> RaceAction["Learn energy plus tactical action"]
    EnergyOnly --> Carry["Carry state across laps"]
    RaceAction --> Carry
    Carry --> End{"More laps?"}
    End -->|Yes| Carry
    End -->|No| Save["Write immutable checkpoint and report"]
    Holdout --> Score["Evaluate with zero updates"]
    Save --> Next["Retain weights and optimizer for next session"]
    Score --> Next
```

```mermaid
flowchart LR
    Observation["Current causal observation"] --> Encoder["Feature mask and normalisation"]
    Encoder --> GRU["Recurrent state"]
    GRU --> Categorical["Masked manoeuvre distribution"]
    GRU --> Beta["Conditional deployment distribution"]
    Categorical --> Sampled["Sampled tactical action"]
    Beta --> Fraction["Sampled electrical fraction"]
    Sampled --> Guard["Availability and rule guard"]
    Fraction --> Guard
    Guard --> Issued["Issued request"]
    Issued --> Allocation["Additive power allocator"]
    Allocation --> Delivered["Delivered power and energy"]
    Delivered --> Reward["Traffic, energy and reserve reward"]
    Reward --> PPO["Recurrent PPO update"]
    PPO --> GRU

    Sampled --> Audit["Sampled action audit"]
    Issued --> Audit
    Delivered --> Audit
```

## Why the two clocks matter

Measured inputs arrive at 4 Hz. The decision engine runs at 5 Hz and explicitly marks when a decision
reuses the latest source frame. It does not interpolate a new measured observation.

```mermaid
sequenceDiagram
    participant Source as 4 Hz source
    participant Hold as Latest-frame holder
    participant Policy as 5 Hz resident policy
    participant Guard as Recommendation guard
    participant UI as Frontend

    Source->>Hold: frame 0 at 0.00 s
    Hold->>Policy: decision 0 at 0.00 s
    Policy->>Guard: action and deployment
    Guard->>UI: decision 0, held=false
    Hold->>Policy: decision 1 at 0.20 s
    Policy->>Guard: action and deployment
    Guard->>UI: decision 1, held=true
    Source->>Hold: frame 1 at 0.25 s
    Hold->>Policy: decision 2 at 0.40 s
    Policy->>Guard: action and deployment
    Guard->>UI: decision 2, held=false
    Source->>Hold: frame 2 at 0.50 s
    Hold->>Policy: decision 3 at 0.60 s
    Policy->>Guard: action and deployment
    Guard->>UI: decision 3, held=false
    Hold->>Policy: decision 4 at 0.80 s
    Policy->>Guard: action and deployment
    Guard->>UI: decision 4, held=true
```

## How runtime inference works

The server accepts registered artifact identities only. Compatibility is checked before checkpoint
loading. Protected targets are referenced but not opened during inference. Recommendations are
sequenced, expiring and auditable. A separate scoring action may open the target after inference has
been frozen.

```mermaid
flowchart TB
    Client["Frontend or registered runner"] --> RunID["Registered run ID"]
    RunID --> Registry["Server-owned artifact registry"]
    Registry --> Manifest["Selection or final-evaluation manifest"]
    Manifest --> Gate{"Identity compatibility"}
    Gate -->|Mismatch| Refuse["Explicit refusal"]
    Gate -->|Match| Load["Restricted checkpoint load"]
    Load --> Resident["Resident recurrent policy"]
    Source["Sealed replay or live 4 Hz observation"] --> Resident
    Resident --> Deadline{"Finite inference deadline"}
    Deadline -->|Valid| Recommendation["Intent and deployment recommendation"]
    Deadline -->|Late or invalid| Hold["HOLD fallback"]
    Recommendation --> Audit["Sequenced JSONL audit"]
    Hold --> Audit
    Audit --> Stream["Read-only stream or duplex live response"]
    Stream --> Frontend["Frontend policy panel"]
    Audit --> Freeze["Frozen inference artifact"]
    Protected["Protected target"] -.-> Score["Separate descriptive scorer"]
    Freeze --> Score
```

```mermaid
flowchart LR
    Reports["Immutable v2 report tree"] --> API["Local read-only report API"]
    Registry["Registered run"] --> Replay["Recommendation stream"]
    Registry --> Live["Duplex live policy socket"]
    API --> Select["Mode, track and 22-profile selector"]
    Select --> Panel["Source-bound report"]
    Replay --> Panel
    Live --> Producer["Future admitted observation producer"]
    Producer --> Panel

    Panel --> Coverage["Qualifying energy or P23 race coverage"]
    Panel --> Advice["Laps, opportunities, actions and events"]
    Panel --> Limits["Unavailable and diagnostic status"]

    Fixture["Clearly labelled fixture world"] --> RaceUI["Full-race visualisation"]
    Panel --> RaceUI
    Limits --> RaceUI
```

## How P23 isolates overtake intelligence

The evaluation adds one independently controlled ego at grid position 23. The original 22 cars use
their fitted ICE profiles and past-only source controls with no electric deployment or tactical
policy. The ego alone receives the learned energy and tactical policy. This isolates profile-policy
differences while keeping the reference field fixed.

```mermaid
flowchart TB
    SourceField["Past-only 4 Hz field controls"] --> Ref1["Reference car 1"]
    SourceField --> Ref2["Reference car 2"]
    SourceField --> RefN["Reference cars 3 to 22"]
    Profiles["Fitted ICE profiles"] --> Ref1
    Profiles --> Ref2
    Profiles --> RefN

    Ref1 --> Fixed["Fixed non-reactive 22-car field"]
    Ref2 --> Fixed
    RefN --> Fixed

    EgoProfile["Selected profile"] --> Ego["Additional P23 ego"]
    EgoPolicy["Learned energy and tactical policy"] --> Ego
    Fixed --> Traffic["Causal gaps and closing speeds"]
    Traffic --> Ego
    Ego --> Decisions["HOLD / ATTACK / DEFEND plus deployment"]
    Decisions --> Progress["Independent proxy progress"]
    Fixed --> Compare["Same-field comparison"]
    Progress --> Compare
    Compare --> Rank["Profile ranking by proxy progress"]
    Compare --> Episodes["Taken and missed opportunities"]
    Compare --> Energy["Deployment, harvest and final store"]
```

```mermaid
flowchart LR
    GapAhead["Ahead gap and closing speed"] --> Opportunity{"Attack opportunity?"}
    GapBehind["Behind gap and closing speed"] --> Threat{"Defence threat?"}
    Brake["Current braking state"] --> Opportunity
    Opportunity --> ActionMask["Tactical availability"]
    Threat --> ActionMask
    Battery["Stored energy"] --> DeployMask["Deployment availability"]
    Throttle["Current demand"] --> DeployMask
    ActionMask --> Policy["Policy decision"]
    DeployMask --> Policy
    Policy --> Episode["Decision episode"]
    Episode --> Taken["Opportunity taken"]
    Episode --> Missed["Opportunity missed"]
    Episode --> Probability["Uncalibrated action-selection probability"]
    Episode --> Power["Requested and delivered power"]
    Episode --> Outcome["Proxy position and gap"]
```

## Measured training and inference results

The six-weekend continuation completed 9,054 cumulative profile updates across 22 policies. Runtime
qualifying reports cover nine training replays plus protected Madring qualifying. Madring supplies
112 accurate laps and 45,426 source ticks for 19 profiles; three profile identities lack complete
accurate laps and produced no substituted data. Its median best idealised additive-power-ratio proxy
is 85.217 seconds. This is not a physical lap-time prediction.

```mermaid
flowchart TB
    TrainResult["22 policies / 9,054 cumulative updates"] --> Qual["10 qualifying report sets"]
    TrainResult --> Race["6 requested race report sets"]
    Qual --> Madring["Madring: 19 supported profiles"]
    Madring --> MadringTicks["112 laps / 45,426 ticks / zero updates"]
    Race --> Complete["4 complete 22-reference races"]
    Race --> Missing["Canada and Monaco unavailable"]
    Complete --> Miami["Miami: median P20"]
    Complete --> Barcelona["Barcelona: median P20"]
    Complete --> Austria["Austria: median P20"]
    Complete --> Britain["Britain: median P20"]
    Miami --> Empty["Median final store empty"]
    Barcelona --> Empty
    Austria --> Empty
    Britain --> Empty
    Missing --> Reason["No tick contains all 22 required references"]
```

| Race | Attack taken | Defence taken | Mean deployment | Mean harvest | Major events |
|---|---:|---:|---:|---:|---:|
| Miami | 122 / 429 | 1 / 436 | 5.454 MJ | 0.567 MJ | 5 |
| Barcelona | 3 / 435 | 1 / 641 | 5.091 MJ | 0.113 MJ | 6 |
| Austria | 556 / 958 | 88 / 939 | 5.136 MJ | 0.170 MJ | 5 |
| Britain | 146 / 599 | 3 / 558 | 5.267 MJ | 0.333 MJ | 7 |

```mermaid
flowchart LR
    Evidence["Observed result pattern"] --> E1["All complete race medians end at P20"]
    Evidence --> E2["All median final stores are empty"]
    Evidence --> E3["Attack rates vary sharply by circuit"]
    Evidence --> E4["Defence is usually missed"]

    E1 --> Diagnosis["Current policy is not race-quality evidence"]
    E2 --> Diagnosis
    E3 --> Diagnosis
    E4 --> Diagnosis

    Diagnosis --> Improve1["Strengthen long-horizon reserve value"]
    Diagnosis --> Improve2["Calibrate tactical action probabilities"]
    Diagnosis --> Improve3["Admit coupled physical and interaction world"]
    Diagnosis --> Improve4["Repeat protected profile-level evaluation"]
```

## What is innovative and what is not yet solved

The innovation is the combination of strict causal evidence, profile-specific recurrent learning,
hybrid tactical and continuous energy actions, separate sampled/issued/delivered records, explicit
4 Hz-to-5 Hz clock handling, and an N+1 controlled field comparison. This is an engineering and
evaluation innovation claim, not a claim that PPO, recurrent networks or energy ledgers are new.

```mermaid
flowchart TB
    Innovation["Integrated decision and evidence architecture"] --> I1["One policy per fitted car profile"]
    Innovation --> I2["Discrete tactics plus continuous deployment"]
    Innovation --> I3["Energy ledger inside every decision"]
    Innovation --> I4["Causal 4 Hz input with explicit 5 Hz holds"]
    Innovation --> I5["Protected optimizer firewall"]
    Innovation --> I6["Additional P23 ego against fixed references"]
    Innovation --> I7["Event-bound lap and race reporting"]

    I1 --> Value["Differences remain attributable"]
    I2 --> Value
    I3 --> Value
    I4 --> Value
    I5 --> Value
    I6 --> Value
    I7 --> Value

    Value --> Solves["Makes energy and overtake decisions trainable, inspectable and comparable"]
    Solves --> Boundary["Does not yet prove physical optimum or real pass success"]
```

```mermaid
flowchart LR
    Initial["Initial problem"] --> Energy["When to spend or recover energy"]
    Initial --> Overtake["When to attack, defend or hold"]
    Energy --> MechanismA["Continuous deployment policy plus signed ledger"]
    Overtake --> MechanismB["Causal traffic classifier plus manoeuvre policy"]
    MechanismA --> MeasurementA["Lap and race energy accounting"]
    MechanismB --> MeasurementB["Taken and missed decision episodes"]
    MeasurementA --> Current["Current diagnostic answer"]
    MeasurementB --> Current
    Current --> Proven["Training and inference path works"]
    Current --> NotProven["Strategy quality and physical accuracy remain unproven"]
    NotProven --> Gate["Admitted physics, calibrated interaction and protected validation"]
```

## Current boundary

The software now trains, checkpoints, evaluates, reports and serves frontend-readable diagnostic
results. It does not yet establish battery truth, calibrated pass probability, real-race rank fidelity
or a 200 ms production guarantee. Those claims remain blocked by physical energy admission, a reactive
interaction world and sustained target-hardware validation.

The report entry point is `data/policy_phase8/runtime_inference_reports_v2/index.json`. The backend
suite passes 421 tests with one performance warning. The frontend production build and touched-file
lint pass; the repository-wide frontend lint retains one unrelated pre-existing effect error.
Raw telemetry exports remain local under the repository data policy. Reports retain their hashes and
provenance, but reproducing training elsewhere requires reacquiring those source exports.
