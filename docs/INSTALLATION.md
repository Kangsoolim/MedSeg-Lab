# Installation · Phase 3B

## Supported baseline

Windows x64; Python **3.11**; Node **22.12+ or 24 LTS**; pnpm **11**. Actual local QA used Python 3.11.17 / Node 24.22.1 / pnpm 11.25.0. Other Python versions are rejected by the installer because their package/adapter behavior has not been validated here. No administrator privileges are expected for a user-owned checkout.

```powershell
.\scripts\Setup-Phase3B.ps1 -Python python
.\Start-Phase3B.ps1 -NoBrowser
```

Open http://127.0.0.1:5173 . Health is http://127.0.0.1:8008/api/v1/health . Ctrl+C shuts down this launcher's processes; it does not stop another pre-existing service. `-CheckOnly` validates imports/build/ports without starting services. `-StopAfterSeconds N` is a bounded QA option, not a training time budget.

## Independent environments

The installer creates a normal venv with `include-system-site-packages = false` and refuses an existing inherited environment. If an older developer venv inherits course packages, preserve it, create a separate checkout, and install there. Do not delete or change the original course environment to make installation pass.

Core versions and their resolved transitive versions are in `backend/requirements-core.lock.txt`; the frontend uses `frontend/pnpm-lock.yaml` with frozen installation. `requirements-core.txt` lists direct pins. Optional neural dependencies are in `requirements-neural.txt`; CPU Torch 2.8.0 comes from the official CPU wheel index, CUDA Torch 2.8.0 from the cu126 index. These are separate explicit installer switches; core installation never requests CUDA wheels. Optional framework transitive inventories record the tested CPU resolution; they are not a portability guarantee across drivers.

The Windows service/worker launcher uses the actual interpreter with `-S` and an explicit venv-derived `PYTHONPATH`. This preserves real process ownership without reinitializing base-interpreter site-packages. Inherited external `PYTHONPATH` should not be used to supply application dependencies. QA records prove that the core-only service reports neural runtime unavailable.

## Optional neural computation

```powershell
.\scripts\Setup-Phase3B.ps1 -Python python -Neural
# OR, for compatible NVIDIA hardware/drivers:
.\scripts\Setup-Phase3B.ps1 -Python python -Cuda
```

CPU supports viewing, analysis, V2, optional U-Net inference and FP32 training. CPU training can be expensive; use explicit small engineering budgets for verification. AMP requires CUDA. CUDA preflight checks actual availability and retains strict checkpoint environment/device signatures. No cross-driver/device exact-recovery guarantee is made.

`checkpoint` is optional and only enables the frozen E17 inference adapter when the file is present; execution also verifies SHA-256 `966a5e59e57d82bd9813ea411735b82256fe6be7114af2d9cde655684d6bfee4`, native checkpoint schema and model settings. Do not download untrusted pickle/checkpoint files. Training can initialize supported models without E17. `source_root` explicitly enables the optional course manifest/history adapter; it is unnecessary for registered datasets.

## Troubleshooting

| Symptom | Action |
|---|---|
| Port already in use | Reuse or stop the owning application yourself. The launcher deliberately does not kill it. |
| Required import missing | Rerun setup in the same checkout; see the import name reported by Check-Environment.py. |
| No Torch/MONAI | Expected for core installation. Choose `-Neural` only if neural computation is required. |
| Input outside allowed folders | Edit local `input_roots` and restart. HTTP requests cannot bypass this policy. |
| No checkpoint / demo package | Normal first-use state. Register your own CT and optional GT. |
| Geometry or binary-label error | Supply aligned 3D millimetre NIfTI and 0/1 masks; correct/resample deliberately outside the app. |
| Indexed history unavailable | Stop the service and remove only the derived `.derived-index.sqlite3` inside the relevant runs root, then restart. Never delete events/records/checkpoints to repair an index. Malformed SQLite headers are also rebuilt automatically. |

Setup accesses official package registries and may use an existing download cache; isolation means no inherited installed packages, not an empty network cache. Windows launcher, fresh core environment, separate CPU-neural environment and physical second-machine coverage are reported independently in QA. **Second physical machine: NOT TESTED.**

## 中文快速开始

先安装 Python 3.11、Node 22.12+ 或 24 LTS、pnpm 11。运行上面的 Setup 与 Start 脚本即可无数据启动。默认不安装 Torch/MONAI；按需加 `-Neural`（CPU）或 `-Cuda`。复制配置示例，填写自己的 `input_roots` 后重启，在欢迎页登记 CT、可选 GT 和预测掩膜。课程目录及权重均为可选资源，不随源码分发。

## Release candidate verification

This clean candidate was actually installed with a new isolated core venv and frozen frontend dependencies. If `python` is not on PATH, pass the actual Python 3.11 executable with `-Python`. Optional CPU neural execution reused the prior isolated environment; fresh CUDA and a second physical machine remain untested. See [candidate QA](RELEASE_CANDIDATE_QA.md) for exact current/prior evidence. Verify the public boundary with `python -B scripts/Verify-PublicSource.py`.
