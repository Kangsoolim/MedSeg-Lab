# Data format and spatial contract

## Phase 2A compatible execution extension

Completed experimental packages add `result_status: "interactive_experimental"` and `run_id`. Methods may carry `result_status` (`interactive_experimental` / `frozen_comparator`), `computed_pred_volume_ml`, and separate `asset_base` / `mesh_base`. These optional additions appear in package.schema.json; no original scientific calculation or frozen CSV field is replaced.

Execution requests use backend/job.schema.json. CT-only registration accepts `{case_id,ct,gt?:null}` without an existing prediction; its preview is an input, never a fake empty prediction. Completed runs use the existing real-mask exporter and fixed loopback artifact URLs. Cross-Run methods retain their own bases to avoid mixing images/meshes.

V2 uses canonical closest-RAS Seed `[i,j,k]` and half-open ROI `[i0,i1,j0,j1,k0,k1]`. Picking inverses the transformed canvas rectangle and display flip/transpose, then applies canonical affine. Six-connectivity belongs to V2; interactive prediction/FP analysis stays 26-connected. PHASE2A_IMPLEMENTATION.md documents the API and isolation contract.

## Import specification

`data_tools/input.schema.json` documents the input JSON. The exporter performs voxel-level validation in addition to structural constraints. `case_id`, `ct`, and at least one prediction are required; GT is optional. IDs are safe ASCII names and may not collide with CT, GT, mesh/label folders, other methods, or generated `_error` modes. Paths in the example are local absolute paths. Image source, algorithm name/version and SHA-256 are retained in case metadata. All CLI output paths must resolve inside this MedSeg-Lab project.

Accepted scope: 3D CT plus spatially aligned binary masks with explicit **mm** units; finite, non-singular effective affine; exactly equal shape and affine agreement with rtol=1e-5, atol=1e-4. Mask voxels are exactly 0/1. Probabilities, multilabels, nonfinite arrays, unknown units and sheared voxel bases are rejected. Orthogonal oblique grids are supported without resampling. Header zooms must agree with the affine basis norms. Empty foreground is represented honestly with zero components and no invented mesh.

Validation happens before case output. CLI import stages the case under a project-local temporary directory and publishes only after success; case ID collisions refuse overwrite and leave the existing index unchanged. The new index is atomically replaced last. Existing course results are never overwritten. Inputs are hashed before and after generic import.

## Package layout

`frontend/public/demo/index.json` lists cases with their individual `case.json` URLs. A case declares effective/native affine, canonical shape, orientation transform, mm spacing, slice-center RAS positions, projected slice position, CT/GT/prediction sources, method/version, optional frozen CSV strings, new statistics, generated timestamp and display/mesh paths. See `package.schema.json` and `frontend/src/types.ts`.

```text
index.json
case_id/case.json
case_id/ct/000.png ...                     fixed HU window grayscale display
case_id/gt/000.png                         optional true-mask display layer
case_id/method_id/000.png                  prediction display layer
case_id/method_id_error/000.png            optional TP/FP/FN display layer
case_id/meshes/gt.mesh                     optional GT surface
case_id/meshes/method_id_1.mesh ...         every predicted 26-component
case_id/meshes/method_id_fp_1.mesh ...      optional FP components
case_id/meshes/labels/method_id/000.png     encoded true component labels
case_id/meshes/labels/method_id_fp/000.png
```

Display PNGs are not quantitative source data. B1 PNGs are copied byte-for-byte and validated against B1 per-slice hashes; imported cases generate their displays from NIfTI. No segmentation is reconstructed from a colored B1 PNG. Contour mode reads the existing display-layer edges for **rendering only**, without deriving any statistics. Quantitative error/component arrays always come from binary NIfTI masks.

Component label transport is a lossless RGB PNG made directly from the real labeled mask: `component_id = R + 256*G`; zero is background. It is separate from colored display overlays. B is reserved. Labels are sorted by voxel count descending, ties stable by scipy scan-label order. More than 65535 components is rejected, not truncated. Browser selection decodes these IDs only to paint an existing component, never to compute scientific metrics.

## Coordinates

NIfTI data remain read-only. Apply the same closest-RAS axis permutation/flip as the source `io_spatial.py`: `ornt_transform(io_orientation(A), axcodes2ornt(RAS))`; canonical affine is `A @ inv_ornt_aff(transform,native_shape)`. No interpolation or voxel-spacing resampling is performed. Axial display is `flipud(RAS[:,:,k].T)`; right R, top A, k zero-based inferior to superior. Image canvas physical aspect is `nx*sx/(ny*sy)`, including imported anisotropic grids. Mask display uses nearest-neighbor pixels.

All panels share k and the same pan/zoom state, hence the same physical slice. `slice_centers_ras_mm[k]` is the exact center world coordinate. The scalar `s` is the projection of that center onto the oriented plane normal; for the three axis-aligned demo cases it equals the S coordinate. For an oblique grid, `s` is **not** mislabeled as patient z.

3D positions are `affine @ voxel_coordinate`; the whole case shares RAS millimetres. Camera fit uses the union of GT and **every** predicted component. Each mesh is not independently recentered or normalized. Slice-plane corners and saved T1/T2 markers use the same affine. A 1.5 mm marker sphere is annotation, not segmentation geometry. No smoothing, decimation or component removal.

## Mesh transport

Little-endian binary `.mesh`: uint32 vertex count, uint32 triangle count; then `vertex_count*3` float32 XYZ positions in RAS mm; then `triangle_count*3` uint32 indices. Marching cubes uses level=0.5, native step=1, one-voxel zero padding, and no degenerates. Padding offset is removed; crop offsets are restored before the full affine. Triangle winding is inverted for negative determinant affines. Every nonempty component, including single voxels, has its own mesh. GT is one full foreground surface. Metadata stores counts, bounds and SHA-256. Browser rejects truncated headers/payloads and reports a real failure with static PNG backup if available.

## Statistics and meaning

26-connectivity is used consistently for predicted foreground and FP regions. Volumes use `abs(det(A[:3,:3]))/1000` mL per voxel. Slice area uses `norm(cross(A[:,0],A[:,1]))` mm² per pixel. TP=prediction∩GT, FP=prediction\GT, FN=GT\prediction. Per-slice counts sum to the corresponding real whole-volume counts.

GT, prediction, FP, FN, net and absolute volume errors are stored separately. Net = prediction−GT = FP−FN; absolute volume error is `abs(net)`, not FP+FN. Frozen results remain original CSV strings in `frozen_metrics`; recomputation goes into `analysis`, with discrepancy checks rather than replacement.

Component metadata includes voxel/physical bounds, centroid, GT intersection and min/max distance to GT voxel centers. `min_distance_to_largest_prediction_mm` is the minimum voxel-center separation to the largest component **of the displayed set** (prediction or FP); the UI labels which set is in use. GT distance uses Euclidean distance transform with physical spacing, valid for the supported orthogonal basis. The 20 mm flag is descriptive, not a clinical threshold or automatic error diagnosis. A prediction component intersecting GT may still contain distant FP; a separate FP component analysis resolves this case.

Without GT: `analysis`, `fp_components`, GT surface and formal overlap metrics are null/unavailable. Predictions, CT and predicted components remain viewable. Future exploratory experiments must use a new result provenance/status and cannot impersonate these frozen course values.

Primary technical references: [NiBabel voxel orientation](https://nipy.org/nibabel/image_orientation.html), [scikit-image marching cubes](https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.marching_cubes), [Three.js](https://threejs.org/docs/), [pnpm build approvals](https://pnpm.io/cli/approve-builds). These libraries are installed locally; the running app does not access these websites.


## Phase 2B additive experiment contract

See [EXPERIMENT_SCHEMA](EXPERIMENT_SCHEMA.md) and [TRAINING_IMPORT](TRAINING_IMPORT.md). Existing case/package, spatial processing and UUID Run History schemas are unchanged. Training histories use experiment schema_version=1, explicit metric definitions, stage/source/hash provenance, null missing values and separate lineage branches. New imports live under the same run root; legacy runs are read-only projections.
