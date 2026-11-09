# Training runtime architecture · Phase 3A

Training is local, opt-in computation. Merely opening Training Workspace, selecting data, changing settings or running preflight never starts a worker. A valid preflight ticket and an explicit `START REAL TRAINING` request are required. Engineering smoke runs are visibly separate from course research results.

## Admission and ownership

`Store` remains the authoritative inference store. `TrainingManager` uses the same `Store.lock`, `Store.active`, service ownership lock and Windows `WorkerOwner` Job Object. There is one active computation across inference and training, rather than one of each. Duplicate request IDs return the same run; reuse with changed configuration is rejected. No Redis, Celery or external scheduler is used.

The API remains on `127.0.0.1:8008`, protected by local Origin/Host checks and the existing per-session write token. The worker command is a fixed Python module and a server-generated UUID directory. HTTP cannot supply commands, executable paths, arbitrary checkpoints or output paths.

All new training output is under `runs/training/<UUID>/`. The existing `run_path` walks each ancestor, rejects traversal, reparse points/symlinks and hardlinked files, and enforces the MedSeg-Lab run boundary. Input reads remain limited by configured `input_roots`; the course repository is never an output target.

Preflight checks actual files, binary GT, matching shape/affine/space, declared membership, duplicate CT content, supplied patient identities, CUDA availability, output writability, free disk, storage quota, estimated global-batch-shuffle RAM and active compute conflicts. Patient identity is not inferred from image appearance. Unknown identity remains an explicit limitation. Course test IDs and known test filenames cannot be selected.

Limits: at most 100 training records, batch size 1–4, total epochs 1–60, one compute worker; engineering runs at most 3 epochs × 1–8 batches, 600 seconds. Explicit full runs have a six-hour process timeout. At least 2 GiB disk headroom is reserved in addition to conservative estimated output. This is an application admission policy, not an OS-enforced memory/disk quota. Full global batching materializes prepared image/GT batches; preflight may reject a complete dataset on a low-memory machine.

## Process state and recovery

State: `queued → preparing → running → stopping → completed / stopped / failed`. `interrupted` identifies backend interruption. Worker events establish actual running/epoch state; persisted stop intent takes precedence. A successful terminal event and exit code zero are both required for completion. Missing terminal events or nonzero process exits become failed, never completed.

The supervisor waits independently of HTTP/browser lifetime. Closing, refreshing or disconnecting the browser does not stop training. On ordinary service shutdown the worker is actually killed and marked interrupted; this is not reported as graceful completion. Abrupt Windows service death closes the kill-on-close Job Object. On startup, matching recorded PID/create-time ownership is checked before orphan termination; active records become interrupted, and checkpoints remain available. Metadata has the existing atomic backup/recovery behavior.

## Events and analytics

Live events use envelope version 2, in `backend/training.schema.json` and `backend/experiment.schema.json`. Every event has UUID `run_id`, monotonically increasing `sequence`, `event_id = run_id:sequence`, timezone-aware UTC timestamp, event type, epoch, optional actual-update step and adapter payload. Historical version-1 imports remain compatible.

Each sequence is a separate atomically published `events/000000001.json` file. One worker owns event writes; the supervisor writes terminal recovery events only after process exit. Temporary/uncommitted files are ignored. Readers never parse a half-appended JSONL line. Event identity is validated before publication. Starting the same request twice is idempotent; event retrieval is read-only and replayable.

The frontend polls every 1.5 seconds, with at most one in-flight polling cycle. `/events?after=N` returns at most 500 committed events and the next cursor. Reconnect continues from the cursor; refresh reloads from zero. A map keyed by sequence prevents duplicate display. A failed request does not advance the cursor. Export includes the complete event history, without the transport page limit. Raw private stderr is not returned as public logs.

`projection()` maps epoch events to the existing `Experiment`/`Epoch` contract. `/experiments` includes live and resumed runs alongside imported training, frozen references and exploratory inference. Existing `TrainingChart` supplies curves, source-aware point inspection, best highlight and SVG export. No second chart implementation or replayed historical stream exists.

Metric semantics: training loss is sample-weighted over finite forward attempts, including AMP skips; `global_step` counts actual optimizer updates. Separate Dice/BCE losses are not computed by the source loop and remain Not Recorded. Validation Dice is only published after all slices of each selected validation patient have been predicted/restored to native space, followed by an arithmetic mean of patient 3D Dice. No slice-average Dice substitutes for this value. Pending values are null/unavailable, never fabricated zero.

## Adapter and source fidelity

`TrainingAdapter` describes validation, dataset preparation, model initialization, training/validation, events, checkpointing/resume, stop and export. The single implementation is `MonaiResidualUNet`, version `monai-resunet-v1`. Seven exact source files are in `backend/vendor/training/src`; `SOURCES.json` records original relative paths and SHA-256. The worker imports only this isolated local source tree.

The original full orchestrator is retained for inspection but is not called. The new adapter calls its computational primitives and the exact source training loop, loss, schedule and validation. Explicit differences are configurable LR/budget, bounded multi-epoch engineering subsets, API monitoring, application checkpoint schema and controlled local output. These runs do not inherit E17 weights or claim to reproduce a historical Stage 7 initialization.

## Checkpoints and stop semantics

Checkpoint schema 3 contains model, Adam optimizer, optional CUDA GradScaler, null scheduler (none is used), complete epoch/update/attempt/AMP counters, best validation state, independent patience reference, history, Python/NumPy/Torch/CUDA RNG, epoch-addressable sampler/schedule state, configuration, data content hashes, executing code hashes, environment and originating run ID. Initial epoch-zero `last.pt` supports safe stopping before the first epoch completes.

Weights are written to a unique temporary file, flushed/fsynced, then atomically replaced. `best.previous.pt` atomically preserves the prior best during the best/last publication window. `last.pt` is updated at each completed configured epoch and `best.pt` follows strictly highest mean Dice. `every_epoch` additionally retains `epoch_NNN.pt`. Patience resets only when score exceeds `patience_reference + min_delta`; a smaller improvement may update best without resetting patience.

Graceful stop persists a STOP request and finishes the current epoch plus validation/checkpoint before terminating. Force termination requires prior graceful stop, an explicit Run ID and a 15-second grace period. It waits for actual process exit and clearly warns that partial progress may be lost. Windows CUDA resources/handles are released with worker exit; the slot is not released while the process is still alive.

Resume is **completed-epoch boundary recovery only**. A partial epoch is replayed from the previous committed boundary. In engineering runs an epoch is the explicitly configured capped batch sequence, not a complete dataset pass. No batch-internal exact resume is claimed.

Preflight and worker verify native checkpoint schema/boundary, architecture/state, optimizer/scaler/RNG presence and finiteness, code/data/config signature and same scientific runtime environment/device. Epoch budget, retention and preview interval may change; learning/data/sampling settings cannot. A new child UUID records parent checkpoint hash and boundary; inherited history is displayed once with lineage, using the validated checkpoint history even if its final parent telemetry event was interrupted. Best checkpoint bytes are inherited with their real original epoch. Historical course checkpoints cannot be resumed through this interface.

## Validation previews and exports

Each real validation writes native-space binary NIfTI plus spatial/metric records. Preview eligibility follows `preview_every`; other epochs explicitly have no preview. The endpoint reuses `export_case`, then the existing imaging workspaces render CT/GT/prediction and TP/FP/FN, 2D slices and available native 3D surfaces. Preview provenance includes epoch, run and mask hash. Inherited previews are resolved to the actual ancestor that computed them.

The logged validation score covers selected full native volumes, not just a preview slice. Engineering subset scores are not full six-patient validation claims. JSONL logs, unified experiment JSON/CSV, existing curve SVG and terminal-run ZIP including checkpoints are local downloads. Medical files, runtime outputs, model weights and private QA evidence are Git-ignored.

## Remaining engineering limits

File-per-event persistence is robust for bounded local acceptance but is not a production telemetry database. Listing/projection and capacity inspection still scan files; very large histories need pagination/indexing in Phase 3B. Cross-device/driver continuation, distributed training, arbitrary model plugins, multi-user isolation and clinical/generalization claims are outside this phase. Registered copied/renamed scans without patient metadata cannot be proven independent or identified as undisclosed held-out copies.

## Final independent acceptance corrections

Checkpoint validation also checks optimizer settings/moments/update counts, real RNG restoration validity, scaler growth/backoff/tracker, selection/history/schedule and the internally recomputed signature. A stop before worker creation now exits without spawning a process or inventing a checkpoint. Force/final cleanup closes the owned Windows Job Object before releasing the slot. Admission rechecks record limits and cross-type UUID identity. Preflight retains one complete tree safety scan, reusing its capacity result; live patience reference derives from committed epoch values. See PHASE3A_FINAL_ACCEPTANCE.md for independently rerun evidence and limits.

## Phase 3B engineering update

Course resources are now explicitly optional; registered datasets and an empty install do not require a course directory. Core CPU imaging/V2 dependencies are separate from optional neural packages. The Windows base interpreter is launched with `-S` and explicit venv paths so global packages cannot leak into an independent installation.

Atomic JSON/checkpoints remain authoritative; a source-stamped SQLite cache now supplies paged events and compact committed projections, and automatically rebuilds after corruption. Per-entry file/link checks and full admission capacity scans remain. Latest-event DOM retention is bounded at 500 while exports retain all committed events. Storage archive leaves checkpoint paths intact; confirmed cleanup is limited to export caches; active/parent-dependent deletion is blocked and tombstones retain provenance. Old code/environment checkpoint fingerprints stay strict. See PHASE3B_IMPLEMENTATION.md and QA for measurements and limitations.
