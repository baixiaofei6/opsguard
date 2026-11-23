# OpsGuard 正式版项目规格（取代 v0.1.0 验证版 TASK.md）

> 地位：把 v0.1.0 的分阶段 demo 升级为**一个可安装的正式 CLI 工具**。本文件取代旧 `TASK.md` 作为开发规格；旧文件保留做历史。
> 关键消歧（用户 2026-11-23 明确）：**"不动系统/本地文件"是约束"我（DSH）在构建与测试过程中的行为"，不是约束"成品软件的能力"**。成品软件必须具备真实修改 Windows（DNS/服务/注册表/文件）的能力；但我开发/测试时不拿用户真实系统做靶子，测试一律用隔离夹具与自建测试环境。
> 追加需求（用户 2026-11-23 开工确认）：**云端 + 本地 AI 混合，预留 API 可插拔接口，给用户选本地的选项，本地后端对接官方下载链接、用户点确认后自动下载安装本地模型**。此需求覆盖旧非目标"本地模型插件不实现"与旧宪法"不引入本地运行时"——以本需求为准。

---

## 0. 目标与成败标准（正式版）

**一句话**：一个可直接使用的 Windows 运维 CLI——`opsguard` 一条命令，覆盖"诊断 / 报告解读 / 带回滚修复"三场景，敢真改系统，且每一步可证明安全（AST 白名单 + 预演 + 确认 + 备份 + 回滚 + 哈希），AI 后端云端/本地/离线三者可切换。

正式版与 v0.1.0 demo 的本质差别：

| 维度 | v0.1.0（验证版） | 正式版（本规格） |
|---|---|---|
| 形态 | c1/c2/c3/C4 四个分散 demo 脚本 | **单一 CLI 入口 + 子命令**，可安装、可 `--help` |
| 系统操作 | 隔离夹具演示，不碰真系统 | **运行时真改 DNS/服务/注册表/文件**，经确认门执行 |
| AI 后端 | 只有本地规则（没接云端、没接本地模型） | **云端 / 本地模型 / 离线规则三选一**，统一 OpenAI 兼容接口，可插拔 |
| 本地模型 | 无 | **对接官方下载链接，用户确认后自动下载安装**（llama.cpp 官方 release + GGUF 模型官方源） |
| MCP | 目录+接口占位 | **可运行薄层**（只读诊断 + 返回建议；执行回 CLI） |
| 既有项目集成 | 样本报告模拟 | **支持为 WinDeploy-Kit / lan-ops-scan 加 `--ai`**（改这两个文件需用户单独授权方可执行） |
| 体验 | 各阶段独立跑、输出各自格式 | 统一 help/错误码/进度/日志/配置/回滚清单/示例 |

**成败**：陌生用户下载后，照 README 三步内能在自己机器上跑通"改 DNS → 备份 → 确认 → 执行 → 回滚 → 哈希验证"；`opsguard doctor` 能自检环境；AI 模式能在云端（有 Key）/本地模型（已安装）/离线规则（都没有）三者间如实切换。

---

## 1. 两条不可混淆的边界（最高优先，违反即返工）

1. **成品能力边界**：软件运行时**允许且应当**真实修改系统（网卡 DNS、Windows 服务、HKCU/HKLM 注册表、指定文件）。这些操作必须：AST 白名单判定 → dry-run 预演（如实标注非沙箱）→ 显式 `y/N`（默认 N、无跳过、无超时自动）→ 备份 → 执行 → 三方哈希验证 → 失败冻结。禁止清单（删服务、格式化、删用户数据、关安全软件）在 AST 层硬拒，确认也不放行。
2. **构建行为边界（约束 DSH/我）**：我开发与测试时**不碰用户真实系统**——真实网卡 DNS、系统服务、系统目录、引导/驱动、任务外文件（默认工作区的 WinDeploy-Kit / lan-ops-scan 除非用户单独授权）一律不动。测试用隔离夹具（临时注册表键 + 临时目录 + mock）+ 真实逻辑链路，证明"变更→备份→回滚→哈希"为真。例外：本地模型"自动下载安装"功能的实现只写下载/校验/启动代码与测试，我构建时不真的下载安装到本地（除非用户要求实测）。

> 一句话记住：**软件能真改；我用假靶子证明它能真改。**

---

## 2. 保留全部已验证的安全资产（不重造、不降级）

从 v0.1.0 原样继承，且保持已通过的测试：
- AST 白名单三态判定（allow_readonly / require_confirm / deny）+ fail-closed + 禁止清单 + 多命令取最严格 tier（防权限提升）。Python `ast_guard.py` + PS `AstGuard.psm1`，对抗 18/18 + 8/8。
- 脱敏层（RFC1918 IP / MAC / 精确主机名 → 占位符，映射留本地，回填还原）。Python `redact.py` + PS `Redact.psm1`，unittest 14/14 + Pester 10/10。
- 安全执行器（备份→执行→三方哈希→回滚→失败冻结）+ 审计日志。Golden 测试 20/20。
- 回滚判定式：回滚后哈希 = 操作前 且 操作后 ≠ 操作前。
- 零第三方运行时依赖：Python 3.8+ 标准库、PowerShell 5.1 自带模块、Pester 3.4（管道 Should 语法）、unittest（禁 pytest）。**本地模型运行时不算 Python 第三方依赖——它是独立可执行程序，通过 OpenAI 兼容 HTTP 接口通信。**
- 视觉规范（深色终端 + 三栏证据卡 + 安全仪表盘配色 + no-color 双通道中文标签 + unified diff + 一句人话）。

复用方式：正式版源码放 `opsguard/src/`，通过 `sys.path` 引入现有 `c1/`、`c2/` 模块（redact / ast_guard / diagnose / generate / policy），**不复制、不重写**这些已验证逻辑；PowerShell 侧复用 `c1/Redact.psm1`、`c2/AstGuard.psm1`、`c2/Policy.psm1`、`c3/*.psm1`。

---

## 3. 要补全的功能（正式版新增，按依赖顺序）

依赖顺序：`统一 CLI 骨架 → 混合 AI 后端 → 真实系统适配器 → 三场景打通 → MCP 薄层 → 既有项目 --ai → 体验优化`。earlier 不依赖 later。

### 3.1 统一 CLI 入口（先做，其余都挂上去）
- 单一入口：`opsguard`（Python `src/opsguard.py` 为主，PowerShell `src/opsguard.ps1` 为辅助包装），`--help` 说人话。
- 子命令：
  - `opsguard diagnose` — 场景①报错排障（本地诊断引擎，输出结论+建议，只读）
  - `opsguard explain <报告文件>` — 场景②报告解读（脱敏 → AI 后端 → 回填 → 三栏证据卡）
  - `opsguard fix` — 场景③带回滚修复（诊断→命令→AST→确认→备份→执行→哈希→回滚/收尾）
  - `opsguard rollback <备份ID>` — 独立回滚（读 manifest，校验哈希）
  - `opsguard audit` — 查审计日志
  - `opsguard backend` — 查看/切换 AI 后端（cloud / local / rules）与状态
  - `opsguard doctor` — 自检环境

  > **实现状态更正（以此为准）**：`install-local` 与本地模型后端已按用户 2026-11-23 裁决**彻底移除**，不再有该子命令；后端仅 `auto/cloud/rules`。以下全局开关清单是初版设想，**多数未实现，不要照抄**：实际只有 `--config <path>`；`--no-color`（CLI 本就无颜色，彩色只在 --tui）、`--quiet`、`--dry-run` 均**不存在**；`--backend` 只在 `explain`/`backend --set` 子命令上，`--confirm`/`--live` 只在 `fix`/`rollback` 上。修改类默认 DRY-RUN 是**内建行为**，不是可加的 `--dry-run` 开关。权威现状见 `README.md` 与 `python opsguard.py --help`。
- （历史设想，已作废）全局开关：`--no-color`、`--backend <cloud|local|rules|auto>`、`--config <path>`、`--quiet`、`--dry-run`。
- 统一退出码（0 成功 / 1 需确认未完成 / 2 被 AST 拒绝 / 3 回滚失败冻结 / 4 参数错误 / 5 后端不可用），写进 README。

### 3.2 混合 AI 后端（预留 API 可插拔接口，云端 + 本地 + 离线）
- 抽象统一接口 `Backend.chat(messages, **opts) -> text`，三实现共用 OpenAI 兼容 chat completions 协议，只是 base_url / key 不同：
  - `CloudBackend`：标准库 `urllib.request` 实现 OpenAI 兼容调用；base_url 与 Key 走配置/环境变量（`OPSGUARD_API_BASE`、`OPSGUARD_API_KEY`），绝不内置 Key、绝不写日志。
  - `LocalBackend`：调用本地 llama.cpp server 的 OpenAI 兼容接口（默认 `http://127.0.0.1:8080/v1`），无 Key。
  - `RulesBackend`：无 Key、无本地模型时的**离线规则模式**，复用现有 `c2/diagnose.py` + `c2/generate.py`，如实标注"离线规则模式"，不包装成 AI。
- `auto` 模式：有 Key 走云端 → 否则本地模型在跑走本地 → 否则离线规则；选择结果如实打印。
- **所有出网 payload 必须先过 `c1/redact.prepare_outbound()`**（云端和本地模型都算"出网"，本地模型即使不联网也走脱敏以防本地日志泄露）；请求发出前断言不含原始 RFC1918 IP/MAC/精确主机名（写进测试，绕过视为失败）。
- 网络失败优雅降级（auto 下退回下一后端），提示用户；断网测试用"DNS 指向不可达地址"，禁用网卡（避免断掉自己的 API 连接）。
- 可插拔：新增后端只需实现 `Backend` 接口并在工厂注册，写进 `src/backends/README.md` 扩展说明。

### 3.3 真实系统适配器（恢复软件能力，构建时用假靶子测）
- 适配器覆盖：网卡 DNS（`Get/Set-DnsClientServerAddress`）、Windows 服务（`Get/Set-Service`）、HKCU/HKLM 注册表项、指定文件路径。
- 每个适配器实现统一接口：采集 before 快照 → 生成变更命令（过 AST）→ 备份（.reg / .bak / 文件副本 + manifest）→ dry-run → 确认 → 执行 → after 快照 → 回滚命令 → 三方哈希。
- 参数化目标（网卡索引、服务名、注册表路径、文件路径由用户指定或交互选择），不写死到某台机器。
- PowerShell 侧复用 `c3/backup_restore.psm1` + `c3/executor.psm1` + `c3/verify_hash.psm1` + `c3/freeze.psm1` + `c3/audit.psm1`；Python 侧写薄封装调用。
- **测试**：用临时注册表键 + 临时目录文件 + mock cmdlet 跑完整链路；不碰真实网卡/服务/系统目录。README 如实写"测试用隔离夹具，运行时按确认可改真系统"。

### 3.4 三场景打通
- diagnose：报错文本/自检结果 → `c2/diagnose.diagnose()` → 建议（只读命令 + 结论），停展示。
- explain：报告 → 脱敏 → AI 后端 → 回填 → 三栏证据卡展示。
- fix：诊断 → 命令 → AST → 确认 → 备份 → 执行 → 哈希 → 回滚/收尾，3 分钟闭环。

### 3.5 MCP 薄层（占位→可运行）
- 同仓库 `src/mcp/` 独立目录，实装最小可跑 server（stdio 或 HTTP 二选一，优先 stdio 零依赖）：暴露只读诊断工具（`opsguard_diagnose`）+ 返回建议文本，**不执行修改**；执行回 CLI。不阻塞 CLI 主线测试。

### 3.6 既有项目 `--ai` 集成（需授权才动那两个文件）
- 提供 `opsguard integrate --target <路径>`：为 WinDeploy-Kit / lan-ops-scan 追加 `--ai` 开关，只在报告末尾插入 section，不改主流程。
- **默认不执行**：目标文件在默认工作区，属任务外文件；只有用户明确授权本次才允许写入，否则只在 opsguard 内生成补丁文件供用户手动应用。

### 3.7 体验优化
- 统一 `--help` 中文说明 + 每个子命令示例；错误给可操作提示（"缺什么、下一步做什么"）。
- 进度输出（诊断中/脱敏中/备份中/已确认/执行中/哈希校验中），可 `--quiet`。
- 集中配置 `src/opsguard.config.json`（API base、Key 环境变量名、日志路径、颜色策略、默认确认行为、本地模型端口），不内置敏感值。
- `opsguard doctor` 自检环境（Python/PS 版本、Pester 版本、云端 Key 是否配置、本地模型是否已安装/在跑、写权限）。
- 统一 README：安装/快速开始/三场景示例/AI 后端三模式/本地模型安装/拦截矩阵/脱敏局限/非目标/故障排查（≥8 条）。

### 3.8 本地模型安装器（用户追加需求，对接官方下载链接）
- `opsguard install-local`：对接**官方**下载链接，用户确认后自动下载安装，全部落到 `opsguard/local/`（任务目录内，不碰系统目录）：
  - 运行时：llama.cpp 官方 GitHub release 的 Windows 预编译包（官方源 `https://github.com/ggml-org/llama.cpp/releases`，给出具体 release URL + 文件名 + 官方 sha256/校验方式，用 `urllib`/`Invoke-WebRequest` 下载）。
  - 模型：官方 GGUF 模型源（如 Hugging Face 上 Qwen2.5-0.5B-Instruct-GGUF 的官方仓库），小体积起步，同样校验。
  - 流程：显示"将下载 X（大小、来源 URL、sha256）→ 用户 y/N 确认 → 下载 → 校验 sha256 → 解压到 opsguard/local/ → 提示可用 --backend local"。默认 N、无静默安装、无系统 PATH 修改、无开机自启。
  - 未实际下载前 doctor 显示"本地模型未安装"；`install-local` 只写下载/校验/解压/启动逻辑与 mock 测试，我构建时不真下载（除非用户要求实测）。
  - 断点续传 / 失败清理临时文件 / sha256 不符即拒绝安装并删除。

---

## 4. 非目标（保持不变，已按新需求修订）

GUI、批量多机、通用 RAG、Prompt 编排、语音助手、任何自动批准/超时执行/跳过确认。这些不排期。
（本地模型运行时不再列为非目标——见 3.8；但"本地模型训练/微调"仍不做，只做下载安装与调用。）

---

## 5. 验收（正式版）

1. 全部继承测试保持全绿：unittest 14+15、Pester 10+32+20、对抗 18+8、夹具清理、护栏 ZERO、Release 哈希。
2. 新增测试全绿：CLI 子命令 help/退出码、云端出网 payload 脱敏断言、本地后端接口契约（mock）、三种后端切换、适配器在假靶子上的备份→回滚→哈希往返、无 Key 降级、本地安装器下载/校验逻辑（mock 下载）、MCP 只读工具。
3. 端到端：陌生用户按 README 三步跑通正式版 fix 闭环（隔离夹具），云端/本地/离线三模式都验证（本地与云端用 mock 验证调用契约，不真下载/不真出网）。
4. ≥5 遍正向测试、每遍找并修 bug，再连跑 2 遍全绿（沿用用户既定验收纪律）。
5. **构建过程护栏**：默认工作区 WinDeploy-Kit（159 文件）/ lan-ops-scan（116 文件）+ 关键脚本零改动，除非用户明确授权 integrate。真实网卡 DNS/系统服务保持原样。

---

## 6. 施工方式（约束）

- 全部代码在 `C:/Users/Administrator/.dsh/im/opsguard/` 内（正式版源码 `opsguard/src/`、测试 `opsguard/src/tests/`、文档沿用根目录）。
- 我（DSH）构建时不碰真实系统/任务外文件；测试隔离夹具；本地模型只写代码不真下载。
- 零第三方运行时依赖、零新增测试依赖；PS5.1 / Python3.8+ 基准（本地模型为独立可执行文件，经 HTTP 调用，不算 Python 依赖）。
- 视觉问题出稿给用户选，不静默拍板（沿用已固化视觉规范，新项走 DECISION-*）。
