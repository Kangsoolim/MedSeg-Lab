# Release candidate handoff — v0.6.0-rc.1

2026-11-09, Asia/Shanghai. Prepared as a clean, local-only source candidate for owner review.

| Decision | Result |
|---|---|
| Release Candidate Technical QA | **PASS**, scoped to tested local Windows Alpha/Preview |
| Public Source Safety | **PASS**, exact final manifest/clean Git boundary |
| Public Release Readiness | **READY FOR OWNER APPROVAL** |
| Second Physical Machine | **NOT TESTED** |
| Publication | No GitHub repository/release, remote or push created |

The independent staging checkout starts from r2's verified 328-file source boundary, with explicit portability/privacy corrections and new audit materials. The final boundary is **342 payload files plus one manifest (343 distribution files)**. Exact hashes and provenance are in `release-manifest.json`; the source delta is in [RELEASE_SOURCE_CHANGES.json](RELEASE_SOURCE_CHANGES.json). The final source ZIP is generated solely from that reviewed manifest. Installed environments and private receipts are not distribution files.

Fresh new core venv + frozen frontend installation/build pass. Backend: 53 passed/13 explicit optional-resource skips; data tools: 22 passed/3 optional classes skipped. Three additional controlled event/idempotency tests passed without training. Empty-install browser: 6 scenarios, no recorded relevant JS errors. Actual service-disconnect and both occupied-port protections pass. A real external CT/GT passes V2, dual-mask numerical crosschecks, 90 slices, native surfaces, history and ZIP export. Actual Chrome quad/spatial/3D navigation passes. CPU E17 passes using the existing isolated Torch 2.8.0+cpu/MONAI environment against staging modules; that optional environment was reused, not freshly installed. No training or clean CUDA install was performed this round.

MIT authorization remains as previously confirmed. Eleven vendored copies retain exact source hashes. Original notices/inventories cover 89 frontend, 34 core, 17 additional neural and 5 Python test packages. Data/weights/results are excluded and gain no redistribution rights from MIT. Screenshots distributed with README show empty setup/disposable engineering storage only.

The sole new root commit and annotated `v0.6.0-rc.1` tag are local review markers. Use `git rev-parse HEAD` and `git show v0.6.0-rc.1` for exact IDs. The public identity is the owner's GitHub noreply identity. No old commit/tag/history or four known private path blobs are inherited. Original repositories remain preserved.

Remaining scope: physical second machine, fresh CUDA/GPU/driver and other OS/browser checks; long workloads; clinical/generalization evidence; exact cross-device/old-code resume. These are explicitly outside this tested Alpha/Preview scope. Second-machine testing is recommended before broader release. Prior training/performance evidence is identified separately in [QA](RELEASE_CANDIDATE_QA.md), never presented as current execution.

Review [source audit](PUBLIC_SOURCE_AUDIT.md), [clean Git setup](CLEAN_REPOSITORY_SETUP.md), [QA](RELEASE_CANDIDATE_QA.md) and [publication checklist](PUBLICATION_CHECKLIST.md). The next publication decision belongs to the owner; no public-upload permission is implied by this handoff.
