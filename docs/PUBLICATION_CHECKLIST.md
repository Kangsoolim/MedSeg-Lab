# Publication checklist — owner review required

**Release Candidate Technical QA: PASS (tested local Alpha/Preview scope).**

**Public Source Safety: PASS (exact final manifest and clean Git objects).**

**Public Release Readiness: READY FOR OWNER APPROVAL.** This is readiness for review, not permission to upload.

- [x] Original r2 membership, sizes, SHA-256 and worktree differences recorded.
- [x] Only reviewed source included; explicit corrections and final manifest retained.
- [x] Independent Git history; four old private blobs absent; no old tags/remotes.
- [x] Owner-selected noreply author identity used only in the new repository.
- [x] Fresh locked core/frontend install, production build and no-data startup verified.
- [x] CPU V2, real multi-mask numerical/2D/3D analysis, history/export and controlled storage/index guards verified.
- [x] Optional CPU E17 executes current staging source; environment reuse disclosed.
- [x] MIT, vendored hashes, dependency/font/icon notices and non-patient screenshots checked.
- [x] External CT/GT/weights remain read-only; private generated run artifacts excluded.
- [x] Owned shutdown and both port-conflict protections verified.
- [x] Local-only RC commit/tag gate met; no public publication action taken.
- [ ] Owner reviews final diff/manifest/notices and explicitly approves any future public upload.
- [ ] Owner selects a public destination and publication scope in a separate action.
- [ ] Recommended: repeat documented installation on a second physical machine.

**Second Physical Machine: NOT TESTED.** Disclose this on any Alpha/Preview page. It does not prevent preparation of this local candidate; stable/multi-platform support and cross-driver/device recovery must not be claimed. Clean CUDA installation and other browsers/OS versions remain untested. No compatibility signatures were relaxed.

For a future upload, publish the reviewed archive or clean commit only, retain license inventories, keep all local data/config/runs private and re-run `scripts/Verify-PublicSource.py`. Any source change requires renewed manifest/hash review and relevant regression. No prior alpha tag or private development history should be added.
