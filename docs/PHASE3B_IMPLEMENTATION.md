# Phase 3B implementation

Baseline: preserved local `v0.5.0-alpha`, commit `b850937027e9e7f5beaf3dbb11ebab77dda555db`. Date: 2026-11-09, Asia/Shanghai. No new segmentation model, full course training, remote configuration, push or stable release tag.

## Release blockers audited first

| Risk | Finding and implementation |
|---|---|
| Private resources at startup | Removed default course/checkpoint/input folders. Empty configuration is valid; course adapter is explicit. Missing demo produces a bilingual welcome/import screen. |
| Python isolation | Added ordinary venv installation and required-import check. Fixed Windows base-interpreter site initialization leaking global packages: owned services/workers now use `-S` with explicit environment paths. |
| Hardware dependency | Imaging/V2 core lock excludes Torch/MONAI. CPU and CUDA optional installation paths are explicit. UI defaults to CPU/FP32; missing neural resources disable computation. |
| Port/process ownership | New launcher refuses occupied ports, validates health PID against the exact spawned process, uses hidden helpers and an owned shutdown-file channel. Normal shutdown invokes app cleanup before bounded kill fallback. |
| History cost | Added SQLite derived event/run-metadata index, compact projection queries, paginated storage summaries and bounded latest-500 event rendering. |
| Long-term storage | Added type/date/status/archive filters, per-run and per-category sizes, file impact review, archive/restore, confirmed export-cache cleanup and dependency-protected deletion with provenance tombstones. |
| Generic input workflow | Added CT/optional-GT registration access without demo and validated multi-mask analysis endpoint. Kept NIfTI geometry, no-resample and binary-mask rules. |
| Publication privacy/legal | Owner confirmed code authorization and MIT. Added license, resolved inventories/notices, sanitized current personal screenshot paths and audited all Git blobs. Historical personal paths remain a publication blocker. |

## Index and recovery contract

`record.json`/backup, immutable atomically committed event JSON and native checkpoints are authoritative. `.derived-index.sqlite3` is disposable; it contains derived event rows and source-stamped metadata only. No old run is migrated or rewritten for indexing. Changed/new/deleted files are reconciled transactionally on every access, using mtime/ctime/size, without a TTL. JSON corruption still follows durable-record backup recovery; index corruption and wrong schemas rebuild from authoritative records.

Each event refresh validates the UUID run/ancestor chain, digit-only source filenames, fresh file type, reparse/link and hardlink attributes. Already validated parent checks are shared within that refresh rather than repeated per file. Only changed event payloads are parsed; requested pages are read from SQLite. Compact projections select committed epoch/checkpoint/resume/status events plus the latest batch. Exports still retrieve the complete event history. Index retries materialize catalog iterables so corruption cannot consume and drop part of a run list.

Safety scans still scale with directory entries; this is not an O(1) telemetry database. Admission/preflight retains a complete capacity/link scan and real input/hash validation. No cache makes an active task state or metric intentionally stale. The existing atomic sequence/event identity/idempotent start mechanisms remain intact.

## Storage safety

Archive changes metadata only and retains original paths/bytes; restore reverses the flag. It is an organization operation and does not reclaim space. Cleanup deletes only a terminal run's regenerable `export.zip`, leaving checkpoints, predictions, previews, raw events and logs intact. Permanent deletion requires full Run ID plus a fresh reviewed impact SHA, rejects any active state/shared active slot, checks direct resume children, revalidates the entire UUID-bound tree and retains metadata/spec/checkpoint hashes in a private tombstone before deleting results. HTTP never supplies a filesystem deletion path. Existing inference delete compatibility routes also require the client-supplied reviewed impact token; their old UI links to the storage-review page instead of bypassing that review.

No automatic deletion/pruning or alteration of real historical runs was performed. Real acceptance outputs remain under new ignored namespaces. Deleting a run is irreversible; archive is the preferred action. This is local single-user protection, not an OS-enforced hostile multi-user sandbox.

## UI and generic scope

Added `Welcome.tsx` and storage controls within the established research-workstation styling. Existing single/dual/quad, error analysis and 3D workspaces remain. The welcome page reports actual configuration, supplies import entry points and keeps English default/Chinese switching. It does not construct mock medical cases. CT-only data can be viewed in algorithm controls without model weights; multi-mask analysis uses the existing viewer and computation/export pipeline.

Supported neural architecture remains `monai-resunet-v1`. No arbitrary-model promise, implicit resampling or clinical claim was added. Frozen course test IDs/known filenames remain blocked even without a configured course directory. Unknown renamed copies cannot be proven independent.

## Compatibility

Native resume checks remain strict for scientific code, data, learning configuration, environment and device. The changed data-resolution wrapper changes its code fingerprint: older checkpoints remain inspectable but are not silently resumable under different code. Keep the frozen tag/environment to resume those runs; no signature override or destructive checkpoint migration was added. New same-code CPU parent/child acceptance is documented separately from prior CUDA acceptance.

See PHASE3B_QA.md, RELEASE_READINESS.md and RELEASE_HANDOFF.md for measured evidence and remaining publication boundaries.
