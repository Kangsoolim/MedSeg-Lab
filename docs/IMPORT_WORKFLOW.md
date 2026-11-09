# Importing NIfTI and supported model resources

## Inputs and analysis

Use **Setup & storage → Setup & import**. Approve folders in local configuration before registration. The server accepts absolute `.nii`/`.nii.gz` files only within those roots; requests cannot supply arbitrary output directories.

Register a unique non-patient-identifying case ID, CT and optional GT. CT must be finite 3D data with valid millimetre geometry. GT and all supplied predictions must match shape/affine and contain exactly binary 0/1 values. Orthogonal oblique data is supported; shear is rejected. No silent resampling is performed.

One CT can be inspected without predictions in **CT & algorithms**, where seed/half-open ROI controls feed Traditional V2. To open comparison/FP/FN/3D analysis, supply one to eight aligned prediction-mask paths, one per line. This performs actual geometry validation, renders the package and persists an `aligned_masks` run. It does not run a new model. GT enables volume Dice/IoU/precision/recall and TP/FP/FN layers; absent GT never produces overlap scores.

`scripts/Import-Case.ps1` remains available for static analysis-package workflows. Keep such packages private because manifests and image assets can contain medical information and source paths.

## Model scope

- Traditional V2: exact vendored seed/ROI confidence-connected and morphology/seed-component code; CPU, no checkpoint.
- E17 inference: the single documented frozen MONAI 2D residual U-Net checkpoint, verified SHA/schema/settings; CPU or available CUDA.
- Training: `monai-resunet-v1`, 1→1 channels, 16/32/64/128/256, two residual units, 256² preprocessing, source-derived loss/batching/native-volume validation. Registered CT/GT pairs support explicit disjoint train/validation selection and supplied patient identities.
- Future architectures need a new adapter implementation and validation. Arbitrary model/weight plug-and-play is **not supported**. Historical course checkpoints are not native training-resume checkpoints.

Course test identifiers and known test filenames remain protected when the optional course adapter is configured. Patient independence cannot be proven from filenames or hashes alone; institution-approved identity governance remains the researcher's responsibility.

## 中文提示

无数据时从欢迎页开始；先配置允许读取的目录，再登记 NIfTI CT 与可选 GT。多个预测掩膜每行一个，最多 8 个。空间必须匹配，不自动重采样；无 GT 不计算重叠指标。当前训练与权重接口只支持文档所述 MONAI residual U-Net，不能把任意模型文件直接接入。真实输入验证范围见 Phase 3B QA，不将合成安装夹具视为医学研究结果。
