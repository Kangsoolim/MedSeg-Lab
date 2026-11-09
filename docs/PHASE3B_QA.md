# Phase 3B QA

Date: 2026-11-09, Asia/Shanghai. **Phase 3B Development QA: CONDITIONAL PASS** for the explicitly tested local scope. **Public Release Readiness: BLOCKED** independently of development test results.

## Environment and installation

Windows x64; Python 3.11.17; Node 24.22.1; pnpm 11.25.0; Chrome. Browser plugin not available; project Playwright/Chrome used. Desktop 1440×1000 and narrow 900×900 were visually inspected. Private JSON/XML/screenshots/logs are under ignored `docs/phase3b`, `.release-qa` or the session visualization directory, not release payloads.

| Check | Actual result |
|---|---|
| New source directory and new core venv | PASS: source-only copy, no Git state/private demo/history/checkpoint/config, `include-system-site-packages = false` |
| Core dependency installation | PASS: independently installed core packages; full 34-package core resolution pinned; frozen frontend lock/build passed |
| Missing neural dependencies | PASS: no Torch/MONAI in core venv; corrected real service reports `training=false`, `neural_runtime=false`, V2 available |
| Separate neural venv | PASS: fresh core install + official Torch **2.8.0+cpu**, MONAI 1.6.1; `torch.version.cuda is None`, CUDA unavailable; neural dependencies inventoried/pinned |
| Package consistency | PASS: pip check reports no broken requirements in both environments |
| Empty data/checkpoint startup | PASS: welcome/import/configuration status, no fabricated metrics, registered-dataset catalog returns empty successfully |
| Port conflict | PASS: occupied local ports rejected without stopping the existing service |
| Owned service lifecycle | PASS: actual startup, health PID identity, frontend availability, timed shutdown; Uvicorn records Application shutdown complete and owned processes exit |
| Actual disconnect | PASS: loaded browser observes real service exit and explicit disconnected state; no route interception |
| Second physical machine | **NOT TESTED**. Independent venvs on this machine are not a second-machine test. |

The first development test run exposed outdated assumptions about implicit course resources and missing-checkpoint admission. Those failures were investigated and retained in logs; lifecycle coverage now uses valid V2 fixtures, missing neural resources are rejected before task creation, and course/demo/neural integration prerequisites are explicit. Optional skipped tests in the core profile were actually run in the configured full profile where resources exist.

## Automated regression

Final configured backend suite: **127 passed, 0 skipped**. Independent core-only profile: **53 passed, 13 explicitly skipped** (optional course/demo/neural prerequisites). The 31 data-tools tests and seven browser scenarios are separate counts; repeated development runs are not added together. Fresh XML/results are summarized in RELEASE_HANDOFF.md. The full configured backend suite exercises existing API/path/link/Windows process ownership/checkpoint state/AMP fixtures plus new Phase 3B behavior. Core-only pytest runs the available profile and explicitly skips private-demo/course/neural prerequisites. The configured data-tools unittest suite has **31 passing tests**. In a source-only installation its private-demo classes explicitly skip; synthetic import/space invariants still run. Production TypeScript/Vite build passed in development and independent directories.

New backend checks include empty settings/catalog, missing neural runtime, 1003-event paging/increment/restart, corrupt SQLite header/schema recovery, complete-catalog replay after recovery, metadata mutation/JSON backup, event identity and hardlink rejection, storage byte categories, archive/restore, explicit impact confirmation, safe cache removal, deletion tombstone, all active states, parent reference protection, paging/date/type filters, traversal, multi-mask geometry mismatch, no-GT metrics, CSRF/session token and retained held-out IDs. Spawn isolation has a separate subprocess regression.

## Browser verification

| Check | Result |
|---|---|
| Identity / meaningful first screen / no framework overlay | PASS at loopback app URL |
| Console/page errors | No relevant JavaScript errors in the 6-scenario main browser run |
| English → Chinese → English | PASS |
| Empty storage filters and pagination | PASS |
| Review → archive → restore → cache cleanup → explicit deletion | PASS using a disposable metadata/cache fixture; no real results deleted |
| Missing neural runtime while service remains connected | PASS |
| Desktop and 900px welcome layout | PASS, screenshots visually inspected |
| Real service termination → disconnected notice | PASS, separate seventh scenario; expected failed network requests after shutdown |

The storage flow initially exposed overlapping async detail requests; review controls now wait for the current operation. The isolation UI initially revealed global package leakage through Windows base Python; `-S` correction was verified with actual CPU-only and missing-neural states. No generated concept art is used in README screenshots.

## Actual data and bounded computation

- Registered and analyzed **spleen_2**, outside the three showcase cases (8/59/17), through the generic workflow with `source_root` empty and explicit read-only input roots. This uses an existing authorized real local CT/GT, **not a newly obtained independent institution/dataset**.
- Actual CPU Traditional V2 used a CT-grid-derived seed/ROI with GT reserved for later analysis. Its final and raw region masks were imported together through the new multi-mask analysis path; geometry, metrics and native surfaces were actually generated. No claim of segmentation quality is made from this engineering selection.
- Actual E17 inference used the explicitly supplied frozen checkpoint with the expected SHA, under the newly installed **CPU-only** wheel. This demonstrates operation without a CUDA runtime, not a physical second CPU-only computer.
- Registered train spleen_56 / validation spleen_9; performed E1 with **one actual optimizer update**, then a new child resumed to E2 with **one additional update**. One full native validation volume per completed boundary. Verified inherited epochs appear once, lineage links to the parent, checkpoint bytes remain available after archive, and the child dependency protects the parent. These two capped configured epochs are not full-dataset passes.
- Existing CUDA/AMP state and worker-process regression fixtures passed in the configured development environment. A new clean CUDA installation, complete multi-epoch dataset training, cross-driver/device exact continuation, and clinical/generalization performance are **NOT TESTED**.

Private receipts: `real-inference.json`, `real-training.json`; runs remain in fresh `runs/phase3b_real_*` namespaces. No real scores, images or weight files enter the source candidate.

## Controlled performance

Same local controlled fixture, 3 samples per path, median wall time. **5,000 batch events and 200 metadata-only runs; no medical model results.**

| Operation | Original file-scan/read path | Indexed/paged path |
|---|---:|---:|
| 500-event page after sequence 4500 | 405.45 ms | 22.54 ms |
| Data retrieval needed for latest-batch projection | 8.047 s (all 5000 JSON payloads) | 49.75 ms (compact required selection) |
| Run catalog vs first storage page | 964.31 ms (all 200 metadata records) | 747.73 ms (25 rows, includes safe size scans) |

Cold construction of the optimized 5000-event index: **0.883 s**. The earlier unoptimized development index took 94.48 s and prompted removal of redundant parent-path checks and batching; its raw evidence is retained rather than substituted as the final measurement. Queries still stat all event entries for freshness/link safety, so growth is not constant time. Run-page comparison deliberately measures different payload sizes; projection measurement is the event retrieval portion, not end-to-end rendered chart latency. No claim is made about throughput on other disks/devices.

## Privacy, provenance and preservation

Audited tracked and new public source plus all **264 Git objects**: no tracked medical/model arrays, no blobs over 1 MiB, no tested secret-pattern hits. Current personal screenshot paths were removed. **Four historical blobs still contain personal directory paths**, and Git author metadata remains; do not push this history as a public repository. Pattern scanning cannot prove absence of all identifiers.

Owner explicitly confirmed code authorization and MIT. Inventories cover 89 frontend/build packages, 34 core packages and 17 additional neural packages, with original notices. Medical resources and real runs remain excluded; no dataset/model redistribution permission was inferred.

Protection receipts compare the initial source/data/checkpoint manifest, the previous 1768-file formal-results protection baseline, all **66869 pre-existing run files**, and every old tag reference. Final exact counts/results are in RELEASE_HANDOFF.md. No old run was archived, cleaned or deleted for QA; storage mutation tests used newly created disposable fixtures only.

## Remaining conditions

Second-machine and clean CUDA/driver/browser coverage, an unrelated external institution/dataset, hostile concurrent local filesystem mutation, exhaustive power-loss/filesystem failure boundaries and long-duration training/storage pressure remain untested. Preflight safety scans still have linear cost; no unsafe cache shortcut was introduced. A version-appropriate code/environment is required for old checkpoint recovery. These limits and the historical-privacy publication block account for the conditional development conclusion.
