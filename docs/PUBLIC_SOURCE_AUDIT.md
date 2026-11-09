# Public source audit — v0.6.0-rc.1

2026-11-09. **Public Source Safety: PASS for the exact final manifest and clean Git object database.** This does not grant data/model redistribution rights or authorize an upload.

## Audited origin and changes

Origin: `medseg-lab-phase3b-source-candidate-r2.zip`, SHA-256 `2097760079eb4214743c236b290dca1def90a846ca0694414cfa0d57326703e9`. All 328 payload files plus `release-manifest.json` matched exact ZIP membership, lengths and SHA-256. The separately generated original manifest matched the ZIP manifest byte-for-byte. No duplicate or unsafe ZIP path was found. All corresponding development working-tree files matched r2. Thirty-nine additional working-tree files were deliberately outside the original packaging boundary; none was silently copied into this candidate.

The original r2 is retained unchanged. Its narrow personal-home-path scan missed development-machine installation/project paths in old helper code, tests and documentation. Therefore it was **not approved unchanged**. Corrections were applied only in the independent staging copy and are enumerated, with before/after hashes, in [RELEASE_SOURCE_CHANGES.json](RELEASE_SOURCE_CHANGES.json). They remove the scientific-package fallback into a host environment; require explicit external paths for legacy helpers/tests; remove stale course defaults/missing-script instructions; fix the Phase 3B browser fixture's output root; add a missing original SVG favicon, complete test dependency notices/pins, update candidate docs/version, and preserve exact source bytes across Git checkouts. Computational vendored modules and strict checkpoint compatibility rules are unchanged.

## Public boundary

The final `release-manifest.json` lists every public payload file with size and SHA-256. Its own bytes are the one explicitly excluded self-entry; the final ZIP includes it. `scripts/Verify-PublicSource.py` checks exact Git-visible membership, all hashes, resource/path/credential exclusions, every stored Git blob, all four known historical private blob IDs, object sizes and absence of remotes. It can produce a ZIP from only that verified boundary.

Excluded: raw NIfTI/DICOM, GT, prediction masks, weights/checkpoints/arrays, actual runs/tombstones/exports, private configs, medical screenshots, private acceptance receipts, virtual environments, installed packages, caches, compiled frontend, and old Git history. Source text and tests were reviewed for machine paths, developer identity and credentials. Generic example input paths and standard Chrome installation paths are intentional templates/system locations. Third-party license authors' required attribution/contact details are retained, not classified as developer privacy leaks. No unreviewed file exceeds 1 MiB in the source/object boundary.

The two existing README PNGs were visually inspected: welcome with no patient data and disposable engineering storage metadata. The added SVG favicon is original project code. New real-data browser validation generated no public medical screenshot. Source artifacts contain no authorized-real-data output.

## Git boundary

New repository initialized without copying `.git`, commits, tags, author metadata, alternates or remotes. All four known historical private path blobs are absent, including unreachable object checks. The original development repository, historical tags and course project remain preserved. The public author identity uses the owner's confirmed GitHub noreply preference; see [setup](CLEAN_REPOSITORY_SETUP.md). A local RC tag is not a public release.

## Licenses and authorization

Project MIT authorization was already explicitly confirmed by the owner and is retained. Eleven vendored copies (nine distinct original module paths) match their source manifests and the read-only original source SHA-256 values. Full notices exist for all inventory entries: 89 frontend/build packages, 34 core Python packages, 17 additional neural packages and 5 additional Python test packages. Font OFL, icon/code MIT, BSD/Apache, MPL/CC-BY/PSF and other recorded terms remain in their original texts. Development-only bootstrap tools are installed by the environment, not bundled in the source payload.

Medical data, predictions, trained weights and patient imagery are not licensed by the project MIT decision and are not redistributed. Testing used previously authorized local resources; no broader institution/dataset authorization was inferred. This is an evidence-backed source/distribution audit, not a blanket upstream license replacement.
