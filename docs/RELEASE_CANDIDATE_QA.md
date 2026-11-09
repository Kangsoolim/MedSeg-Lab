# Release candidate QA — v0.6.0-rc.1

2026-11-09, Asia/Shanghai. **Release Candidate Technical QA: PASS for the local Windows Alpha/Preview scope below.** Public source safety and permission to upload are separate decisions.

## Actual execution in the clean staging source

| Gate | Result and evidence scope |
|---|---|
| Input artifact | r2 ZIP: 328 payload files plus its manifest; exact membership, size and SHA-256 checks pass; no payload differences from the development working tree at audit start |
| Fresh core install | New ordinary Python 3.11.17 venv; include-system-site-packages=false; all 34 core lock entries installed; no installed Torch/MONAI; pip check passes |
| Frontend | Independent frozen pnpm 11.25.0 installation, 89 packages reused from the download store; Node 24.22.1; TypeScript/Vite production build passes, including final favicon/version changes |
| Backend regression | 53 passed, 13 explicit optional-resource skips, 0 failures; one upstream AnyIO deprecation warning |
| Data/spatial regression | 22 executed tests passed; 3 optional private-demo classes skipped |
| No-data startup | Actual owned launcher, frontend HTTP and backend health pass; no input roots, course adapter, checkpoint or neural runtime; traditional_v2=true, devices=[cpu] |
| Empty-install Chrome | Six scenarios pass: truthful welcome, EN/中文, import entry, storage filters, disposable run review/archive/restore/confirmed cleanup/delete, missing-neural training state, 900px layout; no recorded relevant JS errors |
| Lifecycle | Real timed service exit detected in browser; owned backend exits; unrelated controlled listener survives; conflicts at both 8008 and 5173 rejected while existing listeners remain reachable |
| Real external input | Read-only authorized non-showcase CT/GT; source_root empty; actual CPU V2 completed; two generated masks analyzed together |
| Independent numerical check | Two masks independently checked against native voxel counts: Dice, IoU, TP/FP/FN, physical volumes; all match; 90 slice records/images checked, GT mesh and 475 component mesh files generated |
| Real-data Chrome | Run History opens actual multi-mask result; quad comparison, spatial-error volumes and interactive 3D pass; three visible surface objects; reset-view control exercised; no recorded relevant JS errors |
| Results/export | Two completed real run records survive manager reload; actual native result ZIP exports successfully, 8 members, native masks/record present, ZIP integrity passes |
| Optional CPU neural | Current staging backend actually executes E17 with Torch 2.8.0+cpu, CUDA runtime=None, CUDA unavailable, MONAI 1.6.1; supplied checkpoint hash enforced; CT/GT/checkpoint bytes unchanged |
| Event/idempotency supplemental regression | 3 targeted tests passed: retried request identity/body conflict, 2003 committed event sequences with paginated HTTP/complete export excluding uncommitted files, and event cursor/restart. Uses the new core test runner plus existing optional CPU dependencies; no training executed |
| Storage/index regression | Fresh core suite covers 1003-event paging/increment/restart, corrupt header/schema rebuild, complete metadata replay, identity/link rejection, byte totals, 27-run pagination/filtering, archive/restore, fresh impact-token confirmation, cache-only cleanup, tombstones, all active-state and parent/child deletion guards |

The optional CPU environment was **reused** from the previous independently installed environment to avoid repeat downloads. Module-origin evidence verifies that backend/algorithm code came from this staging tree. It is not a fresh neural installation this round. Fresh core installation and all current-source executions above are new evidence. The previous Phase 3B CPU parent/child one-update-per-boundary training evidence and 5000-event/200-run performance measurements are retained as **prior evidence only**, not rerun results. No training was performed this round; strict checkpoint/code/environment/device checks were not weakened.

Private JSON/XML/logs/screenshots and generated medical/engineering run artifacts are outside the public payload. They are never included in the source manifest or ZIP. Real source CT/GT/weights remain external and read-only. No real historical user run was deleted.

## Environment and limits

Windows x64, Python 3.11.17, Node 24.22.1, pnpm 11.25.0, installed Google Chrome via Playwright; 1440×1000 and 900×900 UI checks. Browser plugin not available; project Playwright used. Flow: clean launch → setup/import and storage → real Run History → quad/spatial/3D analysis. Page title/URL, meaningful UI, absence of framework overlay, console health and interactions verified. Welcome/narrow screenshots visually inspected; no UI redesign was needed.

**Second Physical Machine: NOT TESTED.** No accessible configured second physical host was available. Independent venvs on this computer are not second-machine testing. Clean CUDA/cu126 installation, another GPU/driver, other OS/browser combinations, long training, exact cross-device continuation, independent institutional data and clinical/generalization performance are not tested. These are disclosed compatibility limits for the planned Alpha/Preview, not a stable-production support claim. A physical second-machine install is recommended before broader publication.

No unresolved major issue was found within the tested local scope. Known inherited limits remain: linear tree/stat safety scans, archive does not reclaim bytes, private provenance tombstones retain paths, and local single-user operation only. See [publication checklist](PUBLICATION_CHECKLIST.md).

## Reproduction from the reviewed source

```powershell
.\scripts\Setup-Phase3B.ps1 -Python python -Dev
.\Start-Phase3B.ps1 -NoBrowser -StopAfterSeconds 120
.\backend\.venv\Scripts\python.exe -B -m pytest backend/tests -q -ra
.\backend\.venv\Scripts\python.exe -B -m unittest discover -s tests
pnpm --dir frontend run build
.\backend\.venv\Scripts\python.exe -B scripts/Verify-PublicSource.py
```

If Python 3.11 is not on PATH, supply its actual executable to `-Python`; this round used that supported override. Download caches were reused, installed packages were not inherited. Real-input checks require separate explicit authorization/configuration; they are not expected to pass without those optional private resources.
