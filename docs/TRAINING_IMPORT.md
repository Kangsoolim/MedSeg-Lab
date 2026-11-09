# Training history import / 训练日志导入

Install and start from your checkout with `scripts/Setup-Phase3B.ps1` and `Start-Phase3B.ps1`. The public candidate has no course-data default and does not include the historical course-catalog generation script. Set approved external input roots explicitly; generic log import below works without course resources.

## 网页通用导入

打开 Training Analytics 或 Experiments → Import training history：填写唯一 Experiment ID、选择CSV/JSON/JSONL文件、检查原文和来源名称，设置字段映射、指标列及定义，补充实际已知的元数据，然后 Validate and persist import。未连接服务时禁用持久化写入。导入后可选为曲线、比较并导出；刷新和服务重启后从相同 run store 恢复。

支持两种表形状，不提供虚构数值示例：

- 长表列：`experiment_id`（可选但存在时必须一致）、`epoch`、`metric_name`、`metric_value`、`stage`、`timestamp`。JSON 是对应对象数组，JSONL 每行一个对象。
- 宽表：epoch 加实际指标列；`metrics` 将标准指标名映射到输入列。一个文件只包含一个分支；不同分支使用不同实验ID。

例如字段配置（只描述映射，不生成指标值）：

```json
{
  "mapping": {"epoch": "epoch", "stage": "source_stage"},
  "metrics": {"train_loss": "train_loss", "val_mean_dice": "val_mean_dice", "learning_rate": "learning_rate"}
}
```

每个指标必须填写实际 definition、unit、aggregation，不能照抄不适用的项目定义。使用 `val_loss` 可显示真实 Validation Loss；原课程缺少该列，界面显示 Not Recorded。元数据可提供 algorithm、dataset、split_id、case_ids、code_version、device、started_at、ended_at、hyperparameters；不确定的字段保持未知。若原文件没有 stage，不应把多个已知分支拼为一个文件；导入阶段仅说明来自导入记录，不证明训练连续性。转换原日志时在 metadata 保存 original_source 路径/原始哈希及 adapter 说明。

空单元格/JSON null 保留 null；不补0、不插值。拒绝非有限值、损坏JSON/CSV、重复JSON key或CSV列名、重复 epoch+metric（即使同值）、阶段或时间戳冲突、非法Epoch、缺指标定义、ID冲突及完全相同日志内容。长表同Epoch的不同指标允许，但必须属于同一阶段。导入不会静默覆盖；不存在自动合并/append模式。浏览器导入有120秒上限，本机存储容量检查可能耗时；若请求中断，请先刷新确认记录是否已保存，再处理冲突。

导出CSV保留指标定义和来源、分支/划分及metadata；JSON保留完整结构；SVG图表保留原始曲线和来源metadata。JSON导出的完整实验结构不是日志行数组，不能直接当长表再次导入；如需转换应明确映射，并选择不冲突的ID。

## 静态模式

`Start-MedSegLab.ps1` 保留无后端影像分析。生成训练 catalog 后重新生产构建，使静态训练目录进入 dist；修改 catalog 后也需要重新构建生产版本。无Python后端时静态曲线和导出仍可用；动态 Run History、用户导入存储和原始历史mask打开需要本地服务，不将缓存状态称作实时运行状态。


## 最终独立验收后的补充

新导入保留收到的完整UTF-8日志及字段映射回执，可在实验详情下载原始日志；下载前校验内容SHA。旧记录若当时未保留原文，明确返回不可用，不假造来源。ID与原推理运行及冻结参考共用唯一命名空间；不同类型也不能复用同一ID。合法时间须为ISO字符串，case_ids须为字符串数组，超参数须为对象；损坏/截断列、非法类型和非有限元数据都会失败，不写入旧实验。

CSV中不受信任的公式文本（含前导空白/换行）被转义，负数数值不转成文本。冻结CSV的精确原文保存在reference_fields，数值指标及单位分别投影，不将case_id/shape等文本当指标。

较大日志采用明确的轮次窗口和100行分页；超过2000点时要求缩小区间，CSV/JSON仍导出全部原始记录。单点和未记录轮次不会生成补值。可用“Save comparison / 保存比较”保存当前比较到本浏览器，并在刷新/服务重启后恢复；这不是多人共享的服务器比较库。

Historical internal acceptance receipts are excluded from this public source candidate. 本轮用于性能测试的synthetic输入明确标为非训练资料，并原样归档到runs下的独立验收目录，不作为研究历史展示；没有删除真实Run。
