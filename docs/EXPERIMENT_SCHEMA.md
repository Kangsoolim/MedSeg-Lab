# Experiment Schema v1

本契约为 Phase2A 的增量扩展；`backend/contracts.py` / job.schema.json 和旧 Run History JSON 不变。服务健康版本保持 phase2a-v1，兼容原启动器；新功能使用独立 experiment schema_version=1。

## 统一记录

`experiment_id` 为目录唯一标识；training 的 run_id 为真实历史运行ID或导入ID；推理/传统分割的 experiment_id 与现有 UUID Run ID 相同；冻结参考没有伪造 run_id。

核心字段：type (`training|inference|traditional|frozen`)、algorithm、source_kind、status、created_at/started_at/ended_at、dataset、split_id、case_ids、code_version、device、hyperparameters、definitions、sources；可选 checkpoint_sha256/epoch、training_experiment_id、input_hashes、manifest、metrics。无法恢复的信息为 null 或缺省，不使用0补齐。来源名称、代码、路径和指标原文属于可检查的科学元数据，保持原始内容；界面控件与状态说明中英双语。

训练 `epochs[]`：实际 epoch、stage、timestamp|null、metrics{name:number|null}、sources{metric:{path,sha256,line,definition}}、flags、checkpoint|null；课程适配器另带 patients 和 predictions。每条来源可回查原文件哈希。通用导入保留 record_index；CSV/JSONL 另保留实际物理行号（CSV为该记录的终止行），JSON数组不伪造物理行号。`checkpoints[]` 包含真实路径/hash、实际 epoch、schema_version、boundary、模型和 optimizer 张量有限性结果。lineage 的 parent/child/through_epoch/relation 不表示独立重复实验。

`definitions[metric]` 必须记录 definition、unit、aggregation。原课程 val_mean_dice 是六例患者原生全三维 Dice 算术平均，阈值0.5，不是切片平均；Soft Dice 是事后概率统计，不参与选模。learning_rate、loss、ratio、mL 和 s 分开作图。推理 FP/FN 来源于已保存 package 的 analysis.volume；运行时间来自原 result.algorithm_seconds。

## API

| Endpoint | Contract |
|---|---|
| GET /api/v1/experiments | 历史训练 + 新导入 + 原 Run History 投影 + 冻结参考；不复制旧运行 |
| POST /api/v1/experiments/import | HistoryImport；本地 token；201新建、409冲突、422损坏/缺字段/非法数值、413超限 |
| GET /api/v1/experiments/{id} | 完整实验元数据与指标 |
| GET /api/v1/experiments/{id}/export?format=json\|csv | 包含来源、定义及评价上下文 |
| POST /api/v1/experiments/{id}/epochs/{epoch}/analysis/{case} | 仅已核验目录中确实存在的历史预测；不推理；本地token |
| GET /api/v1/historical/{key}/files/{path} | 完整历史分析包的JSON/PNG/mesh；沿用受控路径检查 |

导入 HTTP body 上限1,100,000 bytes，日志 content≤1,000,000 characters，1–20,000 rows，最多1,000训练记录。其他原 API 保持原64KiB限制。日志 SHA 是收到的 UTF-8 content 哈希；若先转换原日志，metadata 应另保存原文件哈希和转换方法。转换后哈希不能冒充原始文件哈希。

## 持久化和恢复

新训练记录位于相同 run root 的 `experiments/<safe ID>/experiment.json` 及 .bak。先完整校验再提交，不允许覆盖；fsync+atomic replace。读取损坏记录时恢复 .bak，保留 corrupt 副本；无有效备份时列入 storage_warnings，不生成假记录。静态来源目录可由只读适配器重建，用户导入不会写入该目录。旧 UUID 记录不迁移、不改变路径，旧 API 不受影响。

浏览器 JSON 导出为 `{schema_version,experiments:[...]}`，API 单条导出为记录对象。CSV 每行一个 epoch/metric，含 stage、timestamp、source/hash、unit/aggregation/definition、split/cases、checkpoint_reference、metadata_json。CSV 对可能被表格软件执行的公式前缀做转义；精确原值可从JSON读取。SVG含图形以及来源/定义的 metadata，不输出平滑数据。

## 历史 v1 训练事件预留

`backend/experiments.py:TrainingEvent`，机器可读 JSON Schema 见 `backend/experiment.schema.json`：run_id、非负整数epoch、可选step、metric_name、有限metric_value、timestamp、event_type (`metric|checkpoint|epoch_end|stopped`)、checkpoint_reference。它是接口预留；本轮没有事件接收/启动训练/实时流服务。未来必须加事件唯一ID/序号、幂等、单位和split关联、单调检查、断点恢复与授权契约，不能用历史播放冒充实时训练。

以上描述属于冻结 Phase 2B 的 v1 兼容契约。Phase 3A 的实际执行契约如下。

## Phase 3A 实时训练增量

`TrainingConfig`、`StartTraining`、`ResumePreflight`、`LiveTrainingEvent` 的完整机器契约见 `backend/training.schema.json`。实验对象仍为 schema_version1，实时事件为schema_version2，原生完整训练checkpoint为schema_version3；版本号分别描述不同对象，不互相替代。

`type=training` 新增 `source_kind=live_training|resumed_training`。历史导入保留 `imported_history|archived_history`，冻结参考与探索性推理保持旧分型。`train_case_ids`、验证 `case_ids`、超参数中的受限批次数/工程标记、代码SHA和父子谱系全部保留。工程短训练不得合并到原课程正式结果；共享前缀不得被计作独立重复。不同验证病例/定义不直接可比；不同学习配置和训练预算应在超参数与谱系下作描述性比较，不推断模型优劣的统计结论。

实时Epoch包含实际metrics、事件文件来源、UTC timestamp、异常/早停flags、逐患者原生3D指标、`preview_available`及实际参数更新证据。`latest_batch`独立于已完成Epoch，避免把当前训练Loss误当验证Dice。`early_stopping`保留best与patience_reference的独立语义。恢复任务的lineage明确parent/child/through_epoch；继承Epoch只显示一次。

| Endpoint | Behavior |
|---|---|
| GET /api/v1/training/catalog | 实际冻结划分、课程/登记病例空间/GT、模型固定配置；不返回测试选择 |
| POST /api/v1/training/preflight | `{config,resume_run_id?,checkpoint}`；检查数据/设备/存储/并发，返回10分钟ticket；不训练 |
| POST /api/v1/training/runs | `{config,preflight_id,request_id,confirm:"START REAL TRAINING",resume_run_id?,checkpoint}`；202，唯一UUID；重复request幂等、不同配置冲突409 |
| GET /api/v1/training/runs | 训练历史、状态、配置、父Run、实际可用checkpoint列表 |
| GET /api/v1/training/runs/{id} | 既有Experiment兼容投影、实际Epoch、最近Batch、谱系和停止原因 |
| GET /api/v1/training/runs/{id}/events?after=N | 最多500个已提交事件，单调sequence和next_sequence；断线补齐 |
| POST /api/v1/training/runs/{id}/stop | 持久安全停止意图；当前配置轮次/验证/权重完成后退出 |
| POST /api/v1/training/runs/{id}/force?confirm={id} | 先请求停止且等待至少15秒；实际结束进程，明确部分轮次丢失 |
| GET /api/v1/training/runs/{id}/logs | 完整实际事件JSONL下载，不受500事件传输页上限限制 |
| GET /api/v1/training/runs/{id}/export | 仅终止任务；ZIP含配置、事件、验证结果、实验和权重 |
| POST /api/v1/training/runs/{id}/preview/{epoch}/{case} | 仅实际已生成的验证病例预测；复用既有export_case；返回现有CaseData |
| GET /api/v1/training/runs/{id}/files/previews/... | 受限的JSON/PNG/mesh分析资产；不能任意读取模型或文件系统 |

所有POST沿用本地session token、Origin/Host和64KiB请求上限。训练与推理使用相同计算锁，默认仅一个计算进程。原 `/runs` 专用于推理，训练在 `/training/runs`；`/experiments`是两者及历史参考的统一投影，不复制/重写原推理记录。

事件的唯一身份为 `run_id:sequence`，UTC时间需有时区。事件存储为原子发布的编号JSON；公开日志不返回原始stderr或凭证。Resume只接受本系统生成、模型/优化器/随机状态和代码/数据/设备环境兼容的已完成Epoch checkpoint。细节见 [训练运行架构](TRAINING_RUNTIME_ARCHITECTURE.md)。


## v0.4.0-alpha independent acceptance corrections

- Experiment ID is one case-insensitive namespace across training, UUID runs and reference records. A conflicting ID is409; no existing record is overwritten. Known metadata fields have validated types, dates are ISO strings, mapped columns are required, and truncated CSV is rejected.
- Every new import retains exact received UTF-8 content and its mapping receipt in `source.json`, with `source_artifact` in the record. `GET /api/v1/experiments/{id}/source` verifies the content hash before returning it. Older records without retained input return404 explicitly; their existing metrics are not migrated or rewritten.
- Reference metadata uses `method_id` to identify exactly the selected method. Only a method with frozen source metrics is classified as frozen. `reference_fields` retains exact original CSV strings; `metrics` contains defined numeric values only. Per-metric units distinguish ratio, voxels, mm3, mL, percent and seconds. Runtime is adapter wall time including analysis export, not a GPU-only duration.
- CSV formula protection applies to untrusted text, including leading whitespace/control characters. Negative numeric metrics remain numeric. JSON preserves exact text. Model weights and native predictions are never altered by this projection.
- Save comparison stores IDs, primary run, metric and inspected Epoch in versioned browser localStorage (`medseg.comparison.v1`). It survives reload and backend restart in that browser; it is not a shared server-side named comparison database. Original sources remain in the authoritative run store.
- Large histories initially display an explicit last-500-Epoch window, with at most2000 raw points. No data is downsampled or discarded; narrowing/altering the range and full exports remain available. Data tables lazily mount at most100 rows per page.
- Request body limits are enforced on actual streamed bytes, not only Content-Length. Transient Windows sharing denials during JSON read retry every20ms, up to1s; permanent denial and malformed JSON remain errors.
