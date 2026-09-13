# Phase 4 handoff

## Current revised Phase 4 status

The active path is direct, source-bound weekend reconstruction. It supersedes teacher-only
fitting as the intended training route. The mechanics interface is stable for downstream offline
work. The final Japan profiles are provisionally promoted under a recorded 6% progress/crossing rule.

Source audit v9 binds the permitted 2026 FastF1 cache and ten sealed race exports. Target artifact
v3 records ten qualifying sessions with 3,817 usable same-segment pairs and ten races with 73,888
usable same-checkpoint gaps. Australia through Britain are training, Belgium is selection, Hungary
and Dutch remain final evaluation, and Italy remains reserved. The final and reserved contents stay unopened.
Australia, China, Japan and Miami qualifying telemetry exports are sealed from copied audit-v9
caches with their session identities, source snapshots and parquet hashes. They are smoke inputs only.
Australia Q has a source-bound closed static route from Q1 driver 27 lap 2. Its 4 Hz labels retain
55,505 of 58,308 joint rows; all controls have declared source brackets through 2.0 seconds and
position labels remain masked beyond 1.1 seconds. The approved 2.0-second linear control estimate
carries an inferred-control mask. A bounded +1.0-second post-lap source search found strict shared
finish crossings for 88 of 91 Q1 laps, 53 of 54 Q2 laps and all 18 Q3 laps. It does not discard
these bounded brackets or validate a race.

The frozen starting architecture is one whole-field logical batch with a 16-value latent per car.
Recorded controls, initial state and source geometry feed shared batched physics; the model produces
its own continuous speed, progress and elapsed time. At 4 Hz, all cars jointly receive rank and
signed-gap loss from common-wall-time progress and matching checkpoint crossings. There is no
motion-loss term: supported full-trajectory motion is a separate 5% admission gate. Each chunk has
exactly one optimizer update.

Implemented pieces are the direct encoder, batched physics path, dense pair objective, source-bound
geometry, trainer, runner and checkpoint backend. Australia qualifying diagnostic v8 passed one
optimizer update on its 18-car Q1 batch. Its batch artifact hash is
`45eff6406147c07b8d31bd723fb3e73b19a29521c4192cd676e284efa2192bb8`; the measured preflight took
9.82 seconds. Its 100-update smoke completed in 892.04 seconds at 8.92 seconds per update and 3.22 GB
peak RSS. Mean loss moved from 1.6110 over the first ten updates to 1.2726 over the final ten; the
checkpoint SHA-256 is `f341eb97a79c00ec7f9e42ee7f39ccc343f18e8c1832bf0d6981299f181ca5f2`.
The admissible path cannot reset from observed telemetry, and a rank head cannot bypass the shared
path. The later bounded race diagnostic anchors each 30-second window from observed state because
the source has gaps; it is explicitly ineligible for that continuous admission gate.

This output is explicitly non-admissible. The diagnostic adapter sets route curvature to zero,
maps Boolean brake-on to 0.2 effective demand and clamps source throttle fractions to `[0, 1]`.
It preserves whole-field physics, rank/gap loss and backpropagation, but cannot pass the motion gate
or freeze a car profile.

Australia entry 55 geometry v5 has 20,273 field-clock rows, 20,096 participant rows and 8,243
source-supported rows, with 33 source-gap laps. Lap adjacency passes, but same-checkpoint support
and full-race support are both false. It is one race diagnostic, not a dataset-wide conclusion.

Australia race diagnostic v2 starts from the v8 qualifying checkpoint and completes exactly one
optimizer update for each of 164 shuffled 30-second batches. Four predictions did not reach every
requested checkpoint, so those batches used their 4 Hz rank pairs only and retained the missing
timing predictions in coverage. Training took 373.03 seconds; frozen evaluation took 175.54 seconds;
peak RSS was 1.36 GB. The checkpoint SHA-256 is
`a0178fd224c2ee73a1f1438a23756c51ab3fde4a98f52852803c7f5f4a547479`.

The final diagnostic evaluates all 164 batches, 4,920 seconds of race clock, 322,707 car-observation
rows and 2,514,380 progress-rank pairs. Progress rank accuracy is 98.924%. Of 8,615 requested timing
pairs, 8,512 are predicted: signed-gap MAE is 1.327 seconds, RMSE is 1.885 seconds, bias is +0.053
seconds and sign accuracy is 97.274%. Speed RMSE is 10.612 m/s, progress-displacement RMSE is
116.840 m and crossing-time RMSE is 1.723 seconds. Their normalized errors are 17.008%, 5.493% and
5.743%, and crossing coverage is 99.321%, so the 5% motion gate fails and remains unavailable.
Predicted timing sigma averages 5.932 seconds, with 99.060% empirical 1-sigma coverage and 100%
2-sigma coverage. These Australia vectors remain intermediate evidence rather than active profiles.

China and Japan race artifacts were both prepared before further optimization, then run one at a
time from the Australia checkpoint. China completed all 185 one-update batches in 534.94 seconds;
78 batches used rank-only timing fallback. Frozen evaluation took 198.37 seconds. Rank accuracy is
95.679%, signed-gap MAE is 2.013 seconds and gap prediction coverage is 89.169%. Speed, progress and
crossing normalized errors are 23.567%, 7.469% and 7.008%. Its checkpoint SHA-256 is
`3967455bf368098308e68492518cd20dca03f9da4a405db9bb152b6d42faaa38`.

Japan then completed 173 of 174 one-update batches in 543.99 seconds; 102 batches used rank-only
timing fallback and one window refused a negative speed or fuel state. Frozen evaluation took 182.82
seconds. Rank accuracy is 97.379%, signed-gap MAE is 1.586 seconds and gap prediction coverage is
92.302%. Speed, progress and crossing normalized errors are 18.643%, 5.620% and 5.580%. Its
checkpoint SHA-256 is
`36454de1415d09065a2261d1b01ffa358add95c4893b8f4768d18f2ac7bb0fe0`.

The final Japan checkpoint was replayed without updates on the earlier Australia and China artifacts.
Australia retains 99.028% rank accuracy and 1.336-second signed-gap MAE; its speed, progress and
crossing normalized errors are 15.964%, 5.005% and 5.445%. China retains 95.451% rank accuracy and
2.177-second signed-gap MAE; its normalized errors are 22.738%, 7.307% and 7.585%. Australia improves
on several diagnostics and China improves speed, progress and timing coverage, but China gap and
crossing errors regress. The sequential run therefore proves that optimization executes and can
transfer improvements; it does not prove convergence or pass the 5% motion gate.

The qualifying and race diagnostics establish executable training, race-wide error and throughput.
They do not establish full physics admission or protected final evaluation.

The user accepted a provisional promotion because Japan progress and crossing errors are both below
6% and the speed error is coupled to declared diagnostic priors. Immutable registry
`promoted_profiles_v1.json` activates 22 profiles from the final Japan checkpoint. It binds the
training report, source profiles and Australia/China retention reports under admission ID
`87daf272e8ec8f275fae47cade4c71f3c6815c617726b3a9756562ae208871c2`. The registry records that
speed admission is waived, physics admission is false and the profiles are compatible with the
downstream profile contract. This is the frozen Phase 4 profile source until it is replaced by a
later version; the source diagnostic artifact remains immutable.

## Current gate and next action

The source audit and qualifying/checkpoint targets are sealed, but continuous full-race trajectory
support is not yet established. The launcher uses the agreed 0.04-second integration step, 0.1 N axle
tolerance and 32 iterations. The user accepted the mechanics interface as stable after the v8
preflight passed. Phase 5 offline response, accounting and historical-rule experiments may now use
that stable boundary after the diagnostic smoke completed.

The provisional profiles may now be bound into downstream offline artifacts and a Phase 5 bundle
with the exact admission identity above. Full physics admission still requires continuous state,
restored curvature, a calibrated brake demand and complete checkpoint predictions. Phase 6 and
Phase 7 retain their independent energy, route, interaction and policy evidence gates; this profile
promotion does not validate their physical or tactical results.

## Historical teacher-only result

The following evidence belongs to the earlier teacher-only Phase 4 route. It is retained for
traceability and does not validate the revised direct reconstruction path.

That route trained GRU and Transformer candidates against numerical teachers fitted from completed
Entry 1 prefixes. Its candidate loss used diagonal Gaussian NLL with variance floor `1e-4`; nonfinite
losses or gradients stopped optimization. The source-binding artifact was retrospective and did not
prove that the original training manifest pinned those sources before training.

The diagnostic used one predeclared two-sample interval. Its maximum reference, refined-step and
stricter-axle differences were `1.0460880162099784e-08`, `5.278096182337322e-09` and
`7.121613464278198e-06` m/s. Its 100-step NLL smoke took 1.133 seconds for GRU and 0.111 seconds
for Transformer; the 80-teacher 1,000-step runs took 10.979 and 1.090 seconds.

Sequential selection retained the numerical baseline. GRU and Transformer MAE were 1.431 m/s and
1.421 m/s against a 1.331 m/s matched baseline on four propulsion rows. Coast and braking were
absent from selection, so promotion was blocked. This was known-input reconstruction over anchored
two-sample intervals; it was not evidence of continuous motion, full-lap fidelity, rank, energy,
source mapping or strategy benefit.
