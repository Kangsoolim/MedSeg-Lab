> Phase 3B: start without course data via Setup & storage; registered CT/GT datasets are supported by the same MONAI adapter. New UI defaults are CPU/FP32. Course examples below require explicit optional configuration. See INSTALLATION.md and IMPORT_WORKFLOW.md. Checkpoint code/environment signatures remain strict; use the frozen version for an older incompatible run.

# Training Workspace / 训练工作台

## 安装与启动

沿用 `scripts/Setup-Phase2.ps1` 和 `Start-Phase2.ps1`。训练额外明确依赖 PyYAML、matplotlib，已加入后端 requirements。既有环境可运行 `backend/.venv/Scripts/python.exe -B -m pip install -r backend/requirements.txt`；不修改原课程 Python 环境。安装 CPU 或 CUDA Torch 的方式见 README。私有数据不随仓库分发，不上传外部服务。

启动网页后进入“训练工作台”。默认配置来自已核验 Stage7，但页面不会自动启动。CPU 需关闭 AMP；选择 CPU 时界面自动关闭它。CUDA 不可用时预检拒绝启动，不静默改设备。

1. 选择已核验课程划分，或已通过算法工作台登记的本地 CT+GT。展开病例表查看维度、间距、方向和 GT。课程训练/验证列表互相受限，不提供正式测试病例。
2. 课程病例选择为空代表使用完整冻结分区；自行导入的数据必须显式选择训练和验证。可选患者标识用于发现不同病例ID下的同一患者冲突。没有患者信息时，平台无法证明完全独立。
3. 设置超参数、设备、权重保留和预览间隔。工程验收使用“工程短训练”：最多3轮、每轮1–8批，选小规模合法子集。这里一轮是配置的受限批次序列，不能冒充完整数据遍历。
4. 点击“运行启动前检查”。检查通过后再点击“确认并开始真实训练”。预检有效期10分钟，修改配置需重新预检。输出目录由后端分配，无法指向原项目/E17。
5. 监控实际 Loss、最新完成的验证轮次与 Dice、LR、更新/尝试批次、状态、曲线和事件。分项 Dice/BCE未单独记录，显示未记录。GT只用于明确的训练损失和验证评价，正式测试集不进入这个流程。
6. “安全停止”会等待当前轮次、验证与权重保存完成。确认任务进入已停止后才释放计算槽。“强制终止”需先请求安全停止并等待至少15秒，可能丢失当前未保存轮次。
7. 选择历史任务，点击“配置恢复训练”，选择 last.pt 或 best.pt，增加总轮次预算，再次预检并确认。恢复只能使用该系统生成且兼容的原生完整状态，产生带父子关系的新Run。不能从任意历史模型权重自动恢复训练。
8. 点击已生成轮次的“打开验证预览”，进入现有二维、误差和三维工作区。它是指定完整验证病例的真实原空间预测；切片显示不等于切片指标替代三维Dice。
9. 导出JSONL真实事件、实验JSON/CSV、曲线SVG，或终止任务的ZIP（包含权重）。刷新后重新选择历史可继续查看。输出均在MedSeg-Lab/runs，Git忽略。

网络临时断开、切换工作区、刷新网页不会取消计算；页面会重连补齐事件。后端进程退出会终止它拥有的工作进程，重启后标记中断。原静态影像/历史曲线仍可在无后端时使用，静态模式不能训练。

## English usage

Start the existing local launcher, then open **Training Workspace**. Select the verified course partition or explicitly assign previously registered local CT/GT cases. Optional patient IDs detect known repeated-patient assignments; absent identity metadata remains an independence limitation. Test cases are excluded.

Configure epochs, batch size, LR, seed, patience/min-delta, CPU/CUDA, AMP, checkpoint retention and preview interval. **Run preflight** only validates. **Confirm and start real training** is the distinct action that launches actual forward/backward/Adam updates. All model/log outputs remain in this repository's private run directory.

For bounded development verification select **Engineering Smoke Test**, a small train/validation subset, at most3 epochs and1–8 batches. Its scores are engineering-subset measurements, never formal course results. A complete run is never started by the smoke tests.

Monitor real committed events and the existing analytics chart. Missing components/validation remain Pending/Not Recorded. **Graceful stop** finishes the current configured epoch and validation, saves checkpoint, then exits. **Force terminate** is separate and may lose the partial epoch. **Configure resume** loads a compatible native checkpoint into a linked child run, using completed-epoch recovery only. Increase the total budget before preflight. Runtime/code/data/learning settings must match.

Open generated validation previews in the existing CT/GT/prediction and TP/FP/FN viewer. Export logs/experiment/curve or a terminal-run ZIP. Refresh/reconnect reloads committed events without duplicates. Disconnecting the browser does not interrupt computation. Without Python the static imaging/history workspaces still work, while training is explicitly unavailable.
