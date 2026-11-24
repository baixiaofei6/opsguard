# OpsGuard —— 可回滚的 Windows 运维 CLI

一条 `opsguard` 命令覆盖三个场景：报错排障、报告解读、带回滚修复。敢真改 DNS / 服务 / 注册表 / 文件，因为每一步都有语法树校验、预演、人工确认、备份、回滚和哈希验证。

AI 后端两档：配了 Key 走云端，没配就走离线规则模式。没有本地模型——断网排障靠的是完备的决策树，不是模型猜测（原因见文末 FAQ）。

Python 3.8+ 纯标准库 + PowerShell 5.1 自带能力，零第三方运行时依赖。

## 两条边界（先读这个）

- **软件运行时**：允许真实修改系统（网卡 DNS、Windows 服务、注册表、指定文件），但必须经过 `AST 白名单 → dry-run 预演 → 显式 y/N（默认 N）→ 备份 → 执行 → 三方哈希 → 失败冻结`。禁止清单（删服务、格式化、删用户数据、关安全软件）在 AST 层硬拒，确认也不放行。
- **本项目的构建与测试**：不拿真实系统当靶子。所有"变更 → 备份 → 回滚 → 哈希"验证都在隔离夹具（临时注册表键 + 临时目录 + mock）里跑；默认工作区的 WinDeploy-Kit / lan-ops-scan 及关键脚本全程零改动。

一句话：**软件能真改；我们用假靶子证明它能真改。**

## 快速开始

入口是 `src/opsguard.py`（需要 Python 3.8+；PowerShell 5.1 用于系统适配）。下文用 `python src/opsguard.py` 表示，装了包装脚本后可直接用 `opsguard`。

```powershell
python src/opsguard.py doctor                      # 自检环境 + 证据链自检
python src/opsguard.py backend                     # 查看当前 AI 后端（含人话降级说明）
python src/opsguard.py diagnose --sample error     # ① 报错排障（只读）
python src/opsguard.py netdiag --catalog           # 断网排障：列出 16 类根因规则卡
```

### 交互界面（Claude Code 风格 TUI，宇宙主题 logo）

新开一个独立窗口最简单的方式：**双击 `启动-OpsGuard.bat`**（会自动用系统 Python，找不到就用 DSH 内置 Python，窗口标题 OpsGuard TUI）。

也可手动起：
```powershell
python src/opsguard.py --tui                       # 进入持续交互界面
```

进入后可连续输入命令。界面参照真实 Claude Code CLI 取证实现（`strings` 抓自本机 claude.exe v2.1.319 + 官方文档）：

- **★ 看这软件能干什么：输入 `/do`** ——弹出核心功能菜单（方向键 ↑↓ 选、Enter 确认、Esc 返回），把 OpsGuard 本身该干的活一条条列出来，每条一句人话说明，选中就用**内置样例/隔离夹具一键试跑真实效果**：★AI 排障对话 ①报错排障 ②断网排障 ③报告解读 ④带回滚修复（演练，不真改）⑤AST 拦截演示 ⑥脱敏证据 ⑦回滚哈希闭环 ⑧拦截矩阵 ⑨环境自检 ⑩后端状态 ⑪审计日志 ⑫生成 --ai 补丁（只预览不写回）。菜单里绝无 `--live`/`--apply`，绝不改你的系统。第一次进来先看 `/do`，这是这软件的主界面。

- **★ AI 排障对话：输入 `/ai`**（或在 `/do` 里选第一项）——像 Claude Code 那样跟 AI 连续对话解决**服务器和电脑问题**（系统/网络/服务/注册表/DNS/网卡）。AI 角色被锁定为运维排障专家，先给结论、再给依据、最后给处置建议；多轮上下文会记住你前面说过什么。对话文本和诊断报告一样先脱敏再出网、回来回填，不泄露内网 IP/MAC/主机名。AI 若认为要改配置，会给出一条修复建议（命令/类型/目标/理由），**先过 AST 白名单判定，再按你选的确认模式处理**。默认只给建议不执行；要执行用 CLI `ai --execute`。**AI 对话需要云端 Key：没配会明确提示你先 `/key add`，不会静默降级**（要故意用离线规则做普通排障，用 CLI `ai --backend rules`）。

- **AI 修复确认模式：输入 `/aimode manual|auto`** ——两种模式随你切、会持久化、状态栏实时显示：
  - `manual`（默认，推荐）：AI 建议改配置时**每次都问你** `[y] 执行 / [N] 取消（默认）/ [a] 看 AST 理由`，默认 N、无超时自动。
  - `auto`（信任模式）：AI 建议改配置时**免逐次问**，但**AST 白名单、备份、三方哈希、失败冻结一道都不少**；AST 判 deny 的动作无论哪种模式都硬拒。auto 只是省掉"逐次问"，不是关掉安全。
  - 无论哪种模式，TUI 里默认都只在**隔离夹具**演练（`/ai` 菜单不碰真系统）；真改系统只能走 CLI `ai --execute --live --confirm y`（manual 要 y，auto 免 y）。readonly 模式下 AI 对话可用但不会执行任何修复。

- **主命令行编辑**（Claude Code 风格）：真终端下主输入行支持 **←→ 移光标、↑↓ 翻历史、Home/End、Ctrl+A/E 到行首/行尾、Ctrl+K/U/W 剪切、Ctrl+Y 粘贴、Alt+B/F 按词移动、Ctrl+R 反搜历史、Esc 清空、回车提交**。非交互/管道仍走普通 readline（兼容）。字符串依据官方文档 interactive-mode 的 Text editing / Command history 表（本机 claude.exe 是 Rust/Bun 打包，strings 抓不到键位表）。
- **Minecraft 式淡字联想**：输入命令时每打一个字母，光标后就显示灰色淡字联想（按命令词库/历史频率），像 MC 输入指令一样。第一次 **Enter 采纳**联想（补全成完整命令/参数），再按一次 Enter 才执行；已是完整命令或无联想时回车直接执行。联想只在光标位于行尾时出现；确认菜单（y/N/d/a）时自动关闭，不会干扰你的选择。无 VT 的控制台降级成 `(联想:xxx)` 文字提示。非交互/管道仍走确定性 readline、不开联想（兼容）。
- **方向键选择菜单**（服务商 / 模型）：`/key add` 填 Key 后、`/model fetch` 拉模型后，会弹出选择清单，**↑↓ 高亮切换、Enter 确认、Esc 取消**（也能直接输序号，兼容管道/非交互）。带计费标注，选哪个就是执行模型。

- **折叠 / 展开**（≈ Claude Code 的 Ctrl+O）：长输出默认压成一行摘要，末尾提示 `/verbose 展开`；输入 `/verbose` 切换全局详细视图。
- **设置面板**：`/config` 查看当前配置，`/config set backend rules` 改配置并落盘（只读模式下不可改）。可设置项只有 `backend` / `timeout_sec`；`confirm_default=no` 是安全红线，恒不可改。
- **权限模式**：`/mode manual|readonly`。只读模式下修复类命令（`fix`/`rollback`/`integrate`）和改配置都被拦；只读命令（`diagnose`/`explain`/`backend`/`doctor`/`netdiag` 等）照常可用。这里的 `manual|readonly` 是**权限档位**；AI 修复的确认模式另由 `/aimode manual|auto` 控制（见上）。**不提供绕过 AST / 跳过备份的 bypass**——那是安全红线，和 Claude Code 有意不同。
- **确认菜单**：修改类命令退出码 1 时显示 `[y] 确认 / [N] 取消（默认） / [d] 看 diff / [a] 看 AST 理由`，菜单列出的键都能直接输入响应，默认 N、无超时自动、无永久免问。告知与真实行为一致：**DRY-RUN 明说"模拟演练、不真改不备份"，只有 `--live` 才提示"将真实改动系统、操作前自动备份"**。
- **打字实时可见**：所有终端输出都 write 后立即 flush（打字内容不再卡在缓冲区）；Windows 控制台启动时自动尝试开启 VT（ANSI 光标控制）。若控制台不支持 VT，输入行自动降级为 `\r` + 可见光标 `│` 标记，界面全程去色纯文本（不留 `\x1b` 乱码）——双击 `启动-OpsGuard.bat` 新窗口里打字也能看见。
- **命令历史**：↑↓（或 Ctrl+P/N）翻本会话历史，`/verbose` 代替真 Ctrl+O 做折叠切换。诚实边界：行编辑只做单行（没有多行输入的光标分支），未做全屏光标导航；Windows 真键盘/真控制台路径用 mock msvcrt + ctypes 覆盖（打字可见两条渲染路径均已单测），未做端到端真按键点击。

宇宙主题 logo：黑洞事件视界 + 三层吸积盘（蓝青/紫/金橙）+ 光子环 + 带环行星 + 星野，逐字符分色，零第三方依赖靠 ANSI 24 位色。静态效果图：`python src/tui.py --html` 生成 `tui-demo.html`。

## 三个场景

```powershell
# ① 报错排障：只读，给结论和建议，不生成也不执行修改
python src/opsguard.py diagnose --evidence "DNS 指向 192.168.1.99 解析失败"

# ② 报告解读：报告文件 → 脱敏 → AI 后端 → 回填 → 展示
python src/opsguard.py explain --report .\samples\sample-windeploy.html

# ③ 带回滚修复：默认 DRY-RUN，不执行、不落盘
python src/opsguard.py fix --sample error --confirm n
# 真改需要同时给出 --live 和显式 --confirm y（默认永不自动执行）
# python src/opsguard.py fix --live --confirm y --kind registry --target "HKCU:\\..." --key Demo --value demo --rollback
```

`fix` 输出包含：发现项、将执行的命令、一句人话、unified diff、AST 三态判定、权限决策、运行模式（DRY-RUN / LIVE）与目标。

AI 排障对话（CLI）：
```powershell
python src/opsguard.py ai --message "Spooler 服务停了，网页打不开，帮我看看"  # 只给建议，不执行
python src/opsguard.py ai --message "DNS 指错了" --mode auto --execute --rollback  # auto 免问执行+回滚（仍夹具）
# 真改系统必须再显式加 --live；manual 模式还要 --confirm y。AST deny 一律不执行。
python src/opsguard.py ai --message "..." --mode manual --execute --confirm y --live --rollback
```
`ai` 输出包含：结论+依据+处置建议（AI 原文）、脱敏/回填统计、实际后端、AI 建议的动作（命令/类型/目标/理由）、AST 判定、确认模式决策、执行/回滚结果。TUI 里用 `/ai` 对话、`/aimode` 切模式。

独立回滚与审计：

```powershell
python src/opsguard.py rollback --manifest <备份manifest.json>       # 按 manifest 回滚 + 三方哈希校验
python src/opsguard.py audit --last 20                               # 查审计日志
```

## 断网排障：16 类根因决策树

用户要"把断网排障规则写完善，尽量覆盖所有遇到的问题"。`netdiag` 是一本纯本地、零依赖、零模型的决策树：

```powershell
python src/opsguard.py netdiag --catalog                             # 全部 16 类规则卡
python src/opsguard.py netdiag --symptom DNS 不可达 网卡 禁用 代理    # 按症状匹配
```

覆盖：DNS 服务器不可达、DNS Client 服务停止、网卡禁用、自动私有地址（DHCP 失败）、默认网关缺失、Winsock 损坏、TCP/IP 协议栈异常、DNS 缓存污染、hosts 劫持、IP 冲突、代理残留、防火墙拦截、网卡驱动异常、IPv6 优先无连通、物理链路断开、事件日志网络错误。

每张卡有：症状模式、根因、置信度、证据检查、只读探针命令、修复命令、回滚命令、一句人话、失败后下一步。修复分两级并如实标注：

- `require_confirm`（2 类，DNS/服务）：命令在 AST 白名单内，走安全门可自动修（默认 N）。
- `manual_only`（14 类）：命令不在自动白名单（netsh / 改 hosts / 插网线等），OpsGuard 给明确指引但**不自动执行**，需人工审核后手动跑——不绕过宪法。

知识库补充命中复用 lan-ops-scan 巡检语料关键词，零依赖检索覆盖长尾症状。

## AI 后端：云端 / 离线两档

统一走 OpenAI 兼容的 `/chat/completions` 协议，可插拔（见 `src/backends/README.md`）：

- **cloud**：标准库 `urllib` 实装 OpenAI 兼容 `/chat/completions`，错误不回显响应体。
- **rules**：无 Key 时的离线规则模式，复用已验证的诊断+命令生成内核，如实标注"离线规则模式"，不包装成 AI。
- **auto**（默认）：有 Key 走云端 → 否则离线规则；降级原因如实打印在 `fallback_from` 与 `effective_detail`。

所有出网 payload 先经脱敏层：RFC1918 内网 IP、MAC、精确主机名替换为占位符，映射只留本地，返回后回填；发出前二次断言不含原始内网 IP/MAC，不满足即拒发。

### 在软件里管理 Key 和模型（输入/删除/更改 + 自由选择）

**不用手填接口地址**：只填 Key 就行。TUI 里 `/key add` 后会让你点一下服务商（编号菜单），地址和默认模型我自动带出——因为 `sk-` 前缀 DeepSeek/百炼/Kimi/OpenAI 都在用，光凭 Key 无法可靠区分，点一下最稳。`sk-proj-`（OpenAI）和智谱的 `id.secret` 格式能自动识别。

**选厂商→发 Key→自动拉模型→看计费→选模型**：`/key add <服务商>` 存好 Key 后会**自动从该厂商官方 `/models` 拉实时模型**，逐个标出官方计费（免费 / 单价 / "价格以官网为准"），再让你输序号选一个设为执行模型。CLI 用 `key add <服务商> --fetch-models`。`/models` 本身只返回模型名、不返回价格，计费来自官方价格页人工整理（`src/pricing.py`，每条带来源链接与核实日期）；没核到单价的如实标"以官网为准"，绝不编造，实际扣费以账单为准。

```bash
# CLI
python src/opsguard.py key suggest                # 先看 Key 会被识别成哪家（不落盘）
python src/opsguard.py key add deepseek           # 随后从 stdin 输入 Key（不回显）；预设自动带接口地址与默认模型
python src/opsguard.py key add                    # 省略服务商：能识别就自动配，识别不出就列可选服务商让你选
python src/opsguard.py key add myvendor --api-base https://llm.example/v1 --models "m1,m2"
python src/opsguard.py key list                   # 只显头4尾4，如 sk-a***bcde
python src/opsguard.py key add deepseek --fetch-models      # 存 Key 后自动拉实时模型+标计费（推荐一站式）
python src/opsguard.py model use deepseek deepseek-flash    # 自由选择执行模型
python src/opsguard.py model fetch deepseek       # 从官方 /models 拉实时模型并标注计费（Codex CLI 做法）
python src/opsguard.py model prices deepseek      # 查官方核价表（本地不出网，逐个模型标计费）
python src/opsguard.py model prices               # 列出所有已收录厂商的核价表来源
python src/opsguard.py model add deepseek my-custom-model
python src/opsguard.py key remove deepseek        # 删除；若删的是当前用到的，自动切到其余可用项
```

TUI 里对应的斜杠命令：`/key`（查看）、`/key add`（只填 Key + 点一下服务商 → 自动拉模型+标计费+方向键选）、`/key remove <服务商>`、`/key fetch <服务商>`（从官方拉模型+标计费）、`/model fetch <服务商>`（拉模型→标计费→方向键选一个，一站式）、`/model prices [服务商]`（查官方核价表，只读不出网）、`/model use|add|remove <服务商> <模型>`。

预设接口地址与默认模型（来自各家官方文档，2026-11 核实；模型名会更新，`model fetch` 可拉实时列表）：

| 服务商 | 接口地址 | 默认模型 | 来源 |
|---|---|---|---|
| deepseek | `https://api.deepseek.com` | deepseek-flash / deepseek-v4-pro | [DeepSeek API 文档](https://api-docs.deepseek.com/zh-cn/)（旧 `deepseek-chat`/`deepseek-reasoner` 已停用） |
| openai | `https://api.openai.com/v1` | gpt-4o-mini 等 | OpenAI 官方 |
| dashscope（百炼） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-plus/turbo/max | [阿里云百炼兼容 OpenAI](https://github.com/enterpilot/gomodel/blob/main/docs/zh/providers/bailian.mdx) |
| moonshot（Kimi） | `https://api.moonshot.cn/v1` | kimi-k3.1-pro 等 | [Kimi API 开放平台](https://platform.kimi.com/docs/get-api-key) |
| zhipu（智谱） | `https://open.bigmodel.cn/api/paas/v4` | glm-4-flash（免费）、glm-4.7-flash、glm-4.6 等 | [智谱 OpenAI 兼容](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction.md) |

> 选模型的实在话：智谱免费档用 `glm-4-flash` / `glm-4.7-flash`（长期 0 元）。同一把 Key 选 `glm-4.6`、`glm-5.3-flash` 等收费模型会返回 `429` / “余额不足或无可用资源包”。**默认已把免费模型排在首位**。`key add` 后可用 `model fetch <服务商>` 从官方 `/models` 拉当前可用的实时模型清单（需 Key 有效）。

安全细节：
- Key 存本机 `.keystore/keys.json`（可用环境变量 `OPSGUARD_KEYSTORE` 改位置），文件权限收紧为**仅当前用户可读**（POSIX 0600 / Windows icacls 精确账户），不加密，所以别把它同步到云盘。
- 该目录已进 `.gitignore`，任何命令输出/日志/测试/交付清单都不会出现明文 Key。
- 接口地址、Key、模型三者永远取自同一处（软件里选的优先），不会出现"甲家的 Key 配乙家地址"的错配；环境变量 `OPSGUARD_API_KEY` 作为旧行为兜底。
- 只读模式下 `/key add|remove`、`/model use|add|remove` 会被拦，查看/列表仍可用。

切换后端：`python src/opsguard.py backend --set cloud|rules|auto`，或用 `explain --backend` 单次覆盖。

## 证据链命令（这个项目的身份证）

产品界面之外，正式版的验收标准是"证据拿得出来"：

```powershell
python src/opsguard.py selftest     # 拦截矩阵：各套件用例数字 + AST 三态当场复判
python src/opsguard.py astcheck     # AST deny 侧：10 条混淆变体逐条拦下
python src/opsguard.py sanitize     # 脱敏证据：出网 payload + 本地映射表
python src/opsguard.py hashdemo     # 回滚三方哈希完整演示（隔离夹具）：before → after → restored + 显式断言
```

这四条覆盖 GLM 缺口清单的核心：拦截矩阵数字、混淆变体 deny、脱敏后 payload、回滚三个哈希值。全部只读或用隔离夹具，不碰真系统。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 需人工确认但未完成（含 DRY-RUN 未确认，非失败） |
| 2 | 被 AST 判定拒绝（deny） |
| 3 | 回滚失败、已冻结 |
| 4 | 参数错误 |
| 5 | 后端不可用 |

## 安全机制

- **AST 白名单**：PowerShell 侧用自带 `System.Management.Automation.Language.Parser` 解析语法树判定三态（只读 / 需确认 / 拒绝），Python 侧同语义镜像；参数缩写、`--%` 停止解析符、反引号、动态命令名、别名覆盖、多命令权限提升一律 fail-closed。对抗测试 Python 18/18、PowerShell 8/8 全过。
- **脱敏后才出网**：见 `c1/README.md` §4 覆盖与局限；RFC1918 三段 + MAC 三变体 + 精确主机名表，映射留本地。局限：只覆盖精确主机名表登记的主机，未登记的内网主机名需显式加入。
- **修改类永不自动执行**：默认 dry-run、默认 N、无超时自动、无跳过开关。
- **可证明安全**：备份 → 执行 → 三方哈希 → 回滚 → 失败冻结；回滚判定式为"回滚后哈希 = 操作前 且 操作后 ≠ 操作前"。审计日志写在 `c3/audit/audit.jsonl`。

拦截矩阵摘要见 `拦截矩阵.md`，完整交付清单与哈希见 `Release-清单.md`。

## 测试

继承资产保持全绿：C1 unittest 14、C2 unittest 15、正式版 unittest 40（后端/MCP/CLI/适配器/断网规则）、C1 Pester 10、C2 Pester 32、C3 Pester 20、AST 对抗 Python 18 + PowerShell 8。一键全量验收：

```powershell
python verify-formal.py 7 1     # 连跑 7 轮（含 ≥5 遍找修 bug + 2 遍确认），含护栏 ZERO / 夹具自删 / 真实 DNS 校验
```

护栏：每轮对比 `baseline.json` 与 `baseline-formal.json`，任务外文件必须 ZERO CHANGES；`HKCU:\Software\OpsGuardTest` 必须不存在；真实网卡 DNS 必须与基线一致。

## FAQ

**为什么断网排障不做本地模型？**
断网排障是个封闭问题域——DNS 通不通、服务在不在、配置和快照一不一致，都是二选一或哈希比对，一张完备的决策树就能 100% 覆盖。本地大模型在这里没有增量，代价却很实在：击穿零依赖、几百 MB 模型文件、要 GPU 或大内存、生成空间变大会给 AST 安全门加压。所以 OpsGuard 的离线诊断不依赖任何模型——因为排障要的是确定性，不是概率。遇到决策树覆盖不了的长尾，正确做法是先写调研报告论证覆盖率不足、修宪法，再决定是否引入，而不是直接塞个模型进来。

**真要改系统，安全吗？**
默认永远 dry-run、默认 N。真改必须同时给 `--live` 和 `--confirm y`，且走 AST 白名单、备份、三方哈希、失败冻结。禁止清单里的动作确认也不放行。构建测试全程用隔离夹具，不碰你的真实网卡/服务。

## 非目标

GUI、批量多机、通用 RAG、Prompt 编排、语音助手、**超时/无人值守自动执行**、**跳过 AST 或备份**的 bypass、本地模型（含下载安装/训练/微调）。为既有项目加 `--ai` 属任务外写入，默认只生成补丁，需用户单独授权才写回（见 `integrate` 子命令）。

> 关于"自动批准"的边界：用户主动开启的 `/aimode auto` 只是让 AI 修复**免逐次问**，AST 白名单、备份、三方哈希、失败冻结全部保留，且 deny 硬拒、超时/无人值守一律不自动执行。这与"跳过安全机制的自动批准"是两回事——后者仍属非目标。

## 文档

`TASK-正式版.md`、`TASK-证据链与交互增强.md`（本次增量规格）、`方案设计-阶段B.md`、`调研报告-阶段A.md`、`DECISION-*.md`、`对抗测试用例清单.md`、`测试记录.md`、`正式版测试记录.md`、`TROUBLESHOOTING.md`（故障排查 11 条）、`回滚失败预案.md`、`运营建议.md`。
