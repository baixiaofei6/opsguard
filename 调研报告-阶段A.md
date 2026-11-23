# OpsGuard 阶段 A 强制调研报告

项目：OpsGuard —— 可回滚的 Windows 运维 AI Agent
阶段：仅阶段 A（强制调研）；不进入阶段 B/C/D
时间盒：≤ 半天；本报告在检索、文档抓取、本机实测后即收敛交付
依据：C:/Users/Administrator/.dsh/im/opsguard/TASK.md（已冻结终稿）

## 0. 证据与边界说明

- 已加载 REA 技能说明；本会话未发现 REA MCP 工具注册。为避免把未发生的逆向当成既成事实，本报告的全网检索由 web_search / web_fetch 完成，REA 的"代码组织与视觉/交互借鉴"按真实检索到的 README、官方文档、文档站 Markdown 与搜索摘要记录；未声称已做二进制逆向或仓库级深度 REA。
- 涉及目标机行为的部分，全部在本机 Windows PowerShell 5.1 实测：PSVersion 5.1.26100.8655，Pester 3.4.0。
- 所有外部来源均给出 URL；凡只能从搜索摘要确认的内容，标为"摘要级证据"，不当作完整源码审计结论。
- 用户偏好：只报告真正抓到的证据与真实做出的动作，不夸大。

## 1. 检索到的同类/参考项目（8 个）

| # | 项目/资料 | 功能证据 | 代码组织可借鉴 | 视觉/交互可借鉴 | 证据状态 |
|---|---|---|---|---|---|
| 1 | Shannot（PyPI 0.11.0） | LLM agent 命令与文件写入先捕获，TUI 审核批准后才应用；diff preview；checkpoint/rollback 会话 | 把"捕获—审核—提交—回滚"做成显式子命令，阶段产物可审计 | TUI 审阅而非静默执行；每次文件修改给出 diff | 搜索摘要：https://pypi.org/project/shannot/0.11.0/ |
| 2 | Claude Code Agent SDK Permissions | 权限按 hooks → deny rules → ask rules → canUseTool 顺序评估；PreToolUse allow 仍受 deny 约束；关键路径删除不可被 hook allow 放行 | 规则分层、拒绝优先、审计链；硬编码关键路径 deny | 权限决策顺序可映射成 CLI 输出里的"判定理由" | 已抓 Markdown：https://code.claude.com/docs/en/agent-sdk/permissions.md |
| 3 | OpenHands SDK Security | 可插拔 SecurityAnalyzer；风险等级 LOW/MEDIUM/HIGH/UNKNOWN；ConfirmationPolicy 决定是否要用户批准；审计事件入 event history | 分析器、策略、审计三件套解耦 | 将风险等级可视化为CLI标签，如 READONLY/CONFIRM/DENY | 已抓 Markdown：https://docs.openhands.dev/sdk/arch/security.md |
| 4 | Aider（permission-gating research / Praxen 分析） | 无 OS sandbox；以 git-undo、edit modes、显式 /run 与 shell confirm 作为安全网；bare Enter 不执行命令 | 版本控制作为恢复兜底；shell 命令显式确认 | "编辑模式"与"运行模式"分离，避免误把建议当执行 | 摘要级：https://github.com/hs3180/disclaude/blob/5f4b1f84bce26e4a6f864cd28aa1bbce1fed173c/docs/pi-permission-gating-research.md ；https://raw.githubusercontent.com/open-agent-ai-security/praxen/46076625bd4bc1f9da2da836735a98a88b021579/tests/baselines/v0.7.7-claude48/aider/aider-analysis-2026-05-29-180535.html |
| 5 | agent-guard | 定位为"带人工升级的自动恢复系统"，默认让破坏性操作可逆；会话级能力，否决为单向降权 | 能力令牌/会话权限与恢复路径分离 | 把"已否决、需人工恢复"做成明确状态，不做 semisilent fallback | 摘要级：https://github.com/mokuyoaxis/agent-guard/blob/88c920f0c15d7178d97b66173762d9a6eab5db47/README.zh-CN.md |
| 6 | Cursor Run Modes | Run Modes：allowlist → sandbox → classifier；terminalAllowlist 支持前缀与参数 glob | 参数级策略与 shell 前端门禁 | diff panel 与权限提示集中展示 | 摘要级：https://github.com/hs3180/disclaude/blob/5f4b1f84bce26e4a6f864cd28aa1bbce1fed173c/docs/pi-permission-gating-research.md ；https://dev.classmethod.jp/en/articles/20260904-cc-updates-v2-1-260/ |
| 7 | llxprt-code Issue #3181 Shell-aware command validation | 明确要求拒绝语法错误树、递归遍历 script block 与子表达式、区分静态可解析命令名和不可安全白名单的表达式 | 将 shell parser 配置与执行配置统一，避免策略层和执行层漂移 | 使用"静态可解析/不可解析"二态理由输出 | 摘要级：https://github.com/acoliver/llxprt-code/blob/78b875db16cf32da3a9f0396bf520595a8363973/project-plans/issue3181/PLAN.md |
| 8 | open-devops-agent | 修复动作在 AUTO_APPLY 与 approval rules 下执行；支持 rollback/restart/config PR；自定义工具带 dry_run 参数 | collector/tool 分层；工具自带 dry_run 入参和状态返回 | dry_run 返回值显式提示"Would restart ..." | 摘要级：https://github.com/open-devops-agent/open-devops-agent |

补充资料：
- xi-agent TUI 对 write/edit 确认框展示完整 diff，预览上限 30 行，提示"...(N more lines)"：https://gitea.florianschroedl.com/floscr/xi-agent/commit/953d12f071b944a7d4fae3c919425d473de15db0
- Windows Optimizer Agent 脚本文档建议注册表变更前建还原点、系统修改函数包裹 SupportsShouldProcess：https://github.com/ven0m0/claude-config/blob/f4761664f7cb6c9e1672e92b51ed1ceca439af78/pi/agents/windows-optimizer.md
- Pester 3/4/5 迁移说明：v4 引入 dashed Should，v5 移除 bareword：https://github.com/github/awesome-copilot/blob/f10fdb8b2660ce85c98f220b2f1ca24653768a5c/skills/pester-migration/references/v3-to-v4.md

## 2. 主题一：AI Agent 安全操作真实系统的业界做法

### 业界做法

- 主流成熟方案把"模型建议"和"系统执行"切开：Claude Agent SDK 用 hooks、deny rules、ask rules、canUseTool 形成多层门禁；OpenHands 用风险分析器与 ConfirmationPolicy 决定是否需要确认，并把决策写入审计事件；Shannot 先捕获 agent 要执行的命令和文件写入，审核后才提交。
- Aider 走另一条路线：没有 OS sandbox，主要靠 git-undo、edit modes、显式 /run、shell 命令 bare Enter 不执行来降低误操作；Cursor 则把 allowlist、sandbox、classifier 做成 Run Modes，并对终端命令做前缀与参数级策略。
- 共同收敛点：每次工具调用前都有 front gate；危险 action 有明确 confirm；拒绝优先于 allow；破坏性操作要么可恢复，要么需要人工升级；输出里必须能看出判定理由。

### 我们采用什么

- 只保留最小闭环：AST 三态判定（allow_readonly / require_confirm / deny）→ dry-run 预演 → diff → 备份 → y/N 默认 N 确认 → 执行 → 审计 → 可验证回滚。
- 修改类命令没有"自动批准""跳过确认""超时默认执行"；禁止清单即使确认也 deny。
- 审计日志每条记录输入摘要、AST 判定、命中节点、确认结果、备份路径、执行结果、回滚记录。
- 参考 Shannot/xi-agent 的审阅体验，确认提示要显示命令、当前值、预期值、备份位置、回滚命令。

### 为什么

- 项目宪法第 4 条要求 AST 白名单静态校验最高优先，禁用正则黑名单；这与成熟方案的 front gate + arg-level policy 同构。
- 项目卖点是"敢执行，因为能证明安全"，不是"模型更聪明"；因此权限判定必须在执行前且可回放。
- 零第三方运行时依赖约束排除 OS sandbox、PyPy 捕获、容器隔离等重方案，保留语法树、备份、哈希这些系统自带能力。

## 3. 主题二：PowerShell AST Parser 白名单 API 与深层绕过手法

### 业界做法

- 微软第一方 API：System.Management.Automation.Language.Parser.ParseInput(string, out Token[], out ParseError[]) 返回 ScriptBlockAst；CommandAst.GetCommandName() 返回静态命令名；Ast.FindAll 可递归遍历节点；StaticParameterBinder 可把命令行参数绑定到命令元数据。本机实测这些类型与重载在 PowerShell 5.1 均存在。
- 社区方案（llxprt-code 计划）强调：拒绝语法错误树；递归遍历 script block 与子表达式；把"静态可解析命令名"和"表达式型命令名"严格区分。
- 学术研究（AST-level deobfuscation / POWERPEER 类工作）通常采用自底向上的 AST 去混淆与语义重建，说明只看文本正则会漏掉结构化变形。

### 本机实测事实（PowerShell 5.1.26100.8655）

- ParseInput 有两个重载，CommandAst.GetCommandName() 存在，StaticParameterBinder 存在。
- Get-Service -Name Spooler：命令名解析为 Get-Service，参数节点清晰。
- Set-Service -Name Spooler -Stat Running：解析无错误，但参数节点仍是 -Stat。这证明参数缩写会出现在 AST 中，白名单若只认 -Status 会误判；必须绑定到规范参数名。
- Get-Service -Name Spooler --% -foo bar：解析无错误，--% 及后续内容成为字符串参数。若只遍历 CommandElements，会把停止解析符后的 opaque tail 当成普通参数，这是深层坑。
- & $n -Name Spooler 与 & ("Ge"+"t-Service") -Name Spooler：解析无错误，但 CommandAst.GetCommandName() 返回 null，第一元素是 VariableExpressionAst 或 ParenExpressionAst/BinaryExpressionAst，必须 fail-closed。
- Invoke-Expression "Get-Service"：能看到 Invoke-Expression 命令节点，应直接 deny。
- PSScriptAnalyzer 规则 UseShouldProcessForStateChangingFunctions 官方说明：状态变更动词函数应支持 ShouldProcess，自动获得 Confirm/WhatIf。

### 我们采用什么

- 解析层：Parser.ParseInput；任何 ParseError 非空即 deny（fail-closed）。
- 遍历层：FindAll 递归覆盖所有 CommandAst、ScriptBlockExpressionAst、PipelineAst 内部节点；脚本块内命令同样按同一规则判定。
- 命令名：只有第一元素为 StringConstantExpressionAst 且 GetCommandName() 命中白名单，才进入参数判定；变量、括号表达式、字符串拼接、成员调用、别名、函数、未知 cmdlet 一律 deny。
- 参数混淆：
  - 建立"规范 cmdlet/原生 exe → 允许参数集合 → 取值约束"白名单。
  - 对白名单 cmdlet 使用 Get-Command 元数据 + StaticParameterBinder 或等价绑定，把 -Stat、-STAT、别名、位置参数解析成规范参数后再比较；不能唯一解析的参数 deny。
  - 大小写不敏感，但参数缩写必须唯一；二义性前缀 deny。
  - 参数值做类型/范围/枚举校验；原生 exe 只认显式列出的参数名和固定值，不接受 opaque tail。
- --% 停止解析符：
  - MVP 直接 deny 任何含 --% token 的脚本。
  - 理由：停止解析后剩余内容按原样传给原生程序，AST 不再给出结构化参数；本项目又要限制原生 exe 参数，放行会破坏白名单语义。
- 动态命令名解析：
  - & $var、. $var、& (expr)、Invoke-Expression、iex、Start-Process powershell -ArgumentList ...、脚本块动态调用全部 deny。
  - 下载执行链、EncodedCommand/enc 按 TASK 直接 deny；不做解码递归，README 如实标注局限。
- 执行一致性：策略判定与执行使用同一份已解析命令对象/同一解析配置；禁止判定后重新拼字符串执行；命令解析优先级需固定，避免 Alias/Function 覆盖 Cmdlet/外部 exe 导致 TOCTOU。

### 为什么

- AST 能看清语法结构，但 PowerShell 的动态特性让"看起来像命令"的东西未必是命令；只有静态字面量 + 唯一参数绑定才可证明。
- 只列 -EncodedCommand、反引号、& $var 三条会漏掉参数缩写、--%、字符串拼接、脚本块内命令、Alias/Function 覆盖；这些恰是 AI 生成变体和脚本混淆常见形态。
- fail-closed 与白名单默认拒绝，和宪法第 4 条、§5.3 完全一致。

## 4. 主题三：dry-run / -WhatIf 在注册表与服务上的真实覆盖与局限

### 业界做法

- PowerShell 的 WhatIf 依赖 CmdletBinding(SupportsShouldProcess) 与 ShouldProcess 调用；PSScriptAnalyzer 有 UseShouldProcessForStateChangingFunctions 规则提醒状态变更函数补齐该能力。
- Shannot/agent-guard 一类方案把"捕获/预演"作为审批前的输入，但不把预演等同隔离沙箱。
- 测试侧用 Pester TestDrive/Mock 验证危险调用参数，而不是真删真改。

### 本机实测事实

- Stop-Service、Set-Service、Set-DnsClientServerAddress 均接受 -WhatIf，并输出 WhatIf 消息；Spooler 服务状态在 Set-Service -Status Stopped -WhatIf 前后均为 Stopped。
- 在已存在的 HKCU 测试键上：Set-ItemProperty -WhatIf 输出"设置属性"消息，值保持 before；New-ItemProperty -WhatIf 输出"新建属性"消息，Probe2 未创建。
- 在不存在的注册表路径上：Set-ItemProperty -WhatIf 仍报"找不到路径……因为该路径不存在"。说明 WhatIf 仍会做目标解析/验证，不是"什么都不碰"的绝对空操作。
- reg.exe add ... /WhatIf 报 ERROR: Invalid syntax.。原生 exe 不享受 PowerShell cmdlet 的 WhatIf 语义。

### 我们采用什么

- 三层预演：
  1. AST 先判定命令是否允许；
  2. 只读采集当前态（注册表值、服务状态、DNS 设置）形成 before 快照；
  3. 对支持 WhatIf 的 cmdlet 附加 -WhatIf 作为第二信号；同时用我们自己的转换规则生成 expected after 与 diff。
- WhatIf 输出只作为证据之一，不作为"执行一定成功/一定无副作用"的真值来源。
- 对不支持 WhatIf 的原生命令（如 reg.exe）：MVP 不走 WhatIf，改为 reg export 快照 + 结构化 diff；若无法形成可信 diff，则 deny 或 require_confirm 后走备份优先。
- 自定义包装函数必须 SupportsShouldProcess，并用 Pester 测试"WhatIf 后无落盘变化"。
- README 和 CLI 文案统一写"预演，不是隔离沙箱"。

### 为什么

- 实测证明常用注册表与服务 cmdlet 的 WhatIf 基本可靠，但也证明目标解析错误和原生命令不支持是真实坑；把它写成万能药会违背 TASK 红线。
- 项目要的是"可证明回滚"，所以 before/after/rollback 三方哈希与备份才是主证据，WhatIf 只是预演证据链的一环。
- 零依赖条件下，自维护 expected-state diff 比引入沙箱现实。

## 5. 主题四：内网信息脱敏正则要点

### 业界做法

- 微软 MIP 日志文档把 IP 地址、MAC 地址、文件名、邮件等列为常见敏感项并支持掩码。
- 隐私日志研究表明 IP/MAC/主机名/文件路径是业界最常脱敏字段；IBM QRadar 等方案按字段隐藏用户名、主机名、NetBIOS 名。
- 实操型工具（Content Scrubber/AiSOC evidence redaction）采用正则 + 精确主机名表 + 占位符替换。

### 我们采用什么

- 出网是单一出口：结构化日志 → 脱敏 → LLM → 占位符回填 → 展示；映射表只留本地。
- RFC1918：10/8、172.16/12、192.168/16，使用边界感知正则并做八位组 0-255 校验；避免把 192.168.256.1 当 IP。
  示例思路（阶段 B 落地前需单测）：
  (?<![0-9.])(?:10(?:\.[0-9]{1,3}){3}|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3})(?![0-9.])
- MAC：覆盖 Windows 连字符、冒号、Cisco 点分与无分隔符变体；无分隔符必须结合上下文或固定 12 位边界，避免误伤版本号。
  示例：([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2} 与 ([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}
- 主机名：按 TASK 硬约束使用精确匹配表，来自本机实际主机名、FQDN、巡检报告出现过的值；按长度降序替换，避免 HOST 与 HOST.domain 互相干扰。禁止用泛正则猜内网主机名。
- 确定性映射：同一原值固定映射到同一占位符（[IP_1]/[MAC_1]/[HOST_1]）；回填还原后再展示；映射日志不随请求出网。
- 局限如实写：公网 IP、用户自定义敏感文件、路径、用户名、IPv6、云元数据等不在 MVP 覆盖内。

### 为什么

- 正则只负责"格式候选"，精确表负责"身份判断"；两者组合才能同时满足召回和不过度脱敏。
- 确定性占位符保留关联推理能力，例如同一 DNS 服务器在日志里多次出现仍是同一实体。
- 宪法第 5 条要求发送前占位符替换、本地存映射；脱敏层必须第一个实现。

## 6. Pester 目标机实测与 3.x/5.x Should 语法差异

### 本机实测

- PowerShell：5.1.26100.8655。
- Pester：Get-Module Pester -ListAvailable 显示 3.4.0，路径 C:\Program Files\WindowsPowerShell\Modules\Pester\3.4.0\Pester.psd1；Import-Module 后 ImportedVersion=3.4.0。
- 真实跑两组最小测试：
  - 1 | Should Be 1：通过（Passed: 1 Failed: 0）。
  - 1 | Should -Be 1：失败，原文 '-Be' is not a valid Should operator.
- Invoke-Pester -Show 在 3.4.0 报"找不到与参数名称'Show'匹配的参数"。
- 官方 Pester 安装文档确认：Windows 10 / Server 2016 及以后随系统带 Pester 3.4.0，内置版本不能通过简单 Update-Module 覆盖；v3→v4 引入 dashed Should，v5 移除 bareword。

### 方案

- 测试源码一律使用 Pester 3.x 语法：Describe/Context/It；断言写成 $x | Should Be 1、$x | Should Throw、$x | Should BeNullOrEmpty 等管道形式。
- 禁止 Pester 5 独有语法：Should -Be、Invoke-Pester -Configuration、-Show、BeforeAll/AfterAll、Run 等。
- CI 加静态检查（Python 标准库或 PowerShell AST 均可，零新增依赖）：扫描 tests 目录，命中 Should\s+-、Invoke-Pester.*-Configuration、-Show、BeforeAll|AfterAll 即失败；同时用 Get-Module Pester -ListAvailable 打印并校验目标机版本为 3.4.x。
- 运行命令使用 3.x 兼容参数：Invoke-Pester -Script <path> -PassThru；不要写 -Show。

## 7. 借鉴点（3-5 条）

1. 借鉴 Claude Agent SDK 的"拒绝优先 + 理由可追踪"：Claude 的 hook allow 也不能越过 deny 规则；OpsGuard 的禁止清单同样压过用户确认。
2. 借鉴 OpenHands 的 analyzer/policy/audit 三段解耦：AST 判定、确认策略、审计日志分开写，便于阶段 B 模块图落地。
3. 借鉴 Shannot/xi-agent 的"审核时看 diff"：确认界面必须显示当前值、预期值、备份路径、回滚命令，长 diff 给折叠提示。
4. 借鉴 Aider 的"编辑/运行模式分离"：C2 只展示方案，C3 才执行；阶段验收不得依赖后置模块。
5. 借鉴 llxprt-code 的"静态可解析/不可解析二分"：动态命令名、变量拼接、脚本块内命令统一 fail-closed。

## 8. 必须规避的坑（3 条）

1. 把 -WhatIf 当万能药：原生 exe 不支持，目标路径不存在时仍会报错，脚本未包 ShouldProcess 时外侧 WhatIf 管不到内部副作用；必须写"预演，不是隔离沙箱"。
2. 参数只看字符串表面：-Stat 缩写、别名、位置参数、--% 停止解析、动态命令名都会让简单比较失真；必须绑定规范参数并 fail-closed。
3. 在测试里混入 Pester 5 语法：本机实测 3.4.0 对 Should -Be 直接报 -Be is not a valid Should operator；CI 静态检查必须拦住。

## 9. 差异化（3 条）

1. 零第三方运行时依赖：Python 标准库 unittest + PowerShell 自带 Parser/Pester 3.4/系统自带 reg export，保证单文件双击能跑。
2. 可证明回滚而非只做撤销：操作前/后/回滚后三方哈希，判定式为"回滚后=操作前 且 操作后≠操作前"；失败即冻结。
3. 三场景复用一内核 + 脱敏先行：脱敏是唯一出网口，AST 三态是唯一命令入口；GUI/批量/本地模型/自动执行明确不做。

## 10. 阶段 A 结论与交接

- 结论：技术路线成立，但安全边界必须建立在"AST 静态可证明 + 默认拒绝 + 预演仅作证据 + 备份哈希回滚 + Pester 3.x 语法锁定"上；任何把 dry-run 当沙箱、把正则当安全门、把离线规则叫离线 AI 的写法都要在阶段 B/C 直接纠正。
- 需父代理转发的视觉/交互拍板项已写入 C:/Users/Administrator/.dsh/im/opsguard/DECISION.md。
- 阶段 A 到此为止；不进入阶段 B。
