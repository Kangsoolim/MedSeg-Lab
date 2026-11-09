# Third-party licenses and provenance

Review date: 2026-11-09. Inventories describe the actual resolved Windows Python 3.11 / frontend installation. Software authorization is separate from medical-data or checkpoint authorization.

## Project and vendored source

The owner explicitly confirmed course-source/new-code authorization and chose MIT in this session. Root `LICENSE` applies to authorized MedSeg-Lab project code. Eleven byte-identical vendored copies, covering nine distinct original module paths, are listed in `backend/vendor/SOURCES.json` and `backend/vendor/training/SOURCES.json`. Retain those manifests and source hashes. No medical data/model rights are inferred from source-code ownership.

## Direct runtime/build dependencies

| Package / source | License / notes |
|---|---|
| [MONAI](https://github.com/Project-MONAI/MONAI/blob/dev/LICENSE) | Apache-2.0; optional adapter runtime, 1.6.1 tested |
| [PyTorch](https://github.com/pytorch/pytorch/blob/main/LICENSE) | BSD-3-Clause plus included third-party notices; CPU 2.8.0+cpu tested separately from local cu126 runtime |
| FastAPI, nibabel, Pydantic, PyYAML | MIT |
| Uvicorn, Starlette, HTTPX, psutil, SciPy, scikit-image | BSD-family; retain full package notices, including compiled dependency terms |
| NumPy | BSD-3-Clause and bundled 0BSD/MIT/Zlib/CC0 notices; see installed-wheel notice inventory |
| SimpleITK | Apache-2.0 and bundled notices |
| Pillow | MIT-CMU / historical PIL terms and bundled notices |
| Matplotlib | Matplotlib license / BSD-style and bundled notices |
| [React / React DOM](https://github.com/react/react/blob/main/LICENSE), Three.js, Vite, lucide-react, i18next/react-i18next | MIT; icon source/attribution notices retained |
| TypeScript, Playwright | Apache-2.0; development dependencies |
| Inter Variable, Noto Sans SC | SIL OFL-1.1; complete existing OFL texts retained. Font assets are bundled locally and not fetched from a CDN. |

Full inventories contain exact versions, declared expressions, package source/project URLs and retained notice filenames:

- `docs/licenses/frontend-inventory.json`: 89 resolved frontend/build packages. Full notices are under `docs/licenses/npm/`; three native companion build packages inherit the corresponding esbuild/Rollup notice, explicitly marked in inventory.
- `docs/licenses/python-core-inventory.json`: 34 resolved core packages; notices under `docs/licenses/python/`.
- `docs/licenses/python-neural-inventory.json`: 17 additional neural packages and their full notices. Core dependencies are not duplicated in this inventory.

Transitive exceptions deserve explicit visibility: certifi uses MPL-2.0; caniuse-lite build data uses CC-BY-4.0; typing-extensions uses PSF-2.0; packaging offers Apache-2.0 OR BSD-2-Clause. Their original materials and attribution are retained. MIT for MedSeg-Lab does not replace these terms. Packages are installed from their registries, not relicensed or copied into project source. This inventory is an engineering compliance review, not a claim that all upstream distributions share one license.

## Medical resources, screenshots and examples

No CT, GT, predicted medical mask, pretrained weight or real run is distributed. The real workflow acceptance reads an existing local Medical Segmentation Decathlon Task09 resource set; this does **not** establish permission to redistribute local copies or derived patient images. Dataset-specific terms and institutional approval must be reviewed independently before any future redistribution. No sample medical dataset is included.

The two README screenshots were captured from the running application: an empty install and a disposable metadata/cache fixture. They contain no patient image, real patient identifier, local input path or private model content. Source-only release packaging excludes private QA screenshots, logs, run manifests, exports and checkpoints.

Synthetic unit arrays and controlled telemetry fixtures are explicitly labeled engineering tests. They are not medical research outcomes, and no benchmark claim is made from their generated overlap values.

## Publication boundaries

Publish only the reviewed source candidate described in RELEASE_READINESS.md. Preserve license files and inventories with any redistributed build. Do not publish this local Git history automatically: it contains historical machine paths and author metadata despite current-source sanitization. No remote, upload or public release was configured by this work.

## Release-candidate additions

`docs/licenses/python-dev-inventory.json` records the five resolved optional pytest/test dependencies, with retained original license texts under `docs/licenses/python/`. The development requirement file now pins this complete tested resolution. The small source SVG favicon is original MedSeg-Lab project code under MIT. No external image or medical asset was added.
