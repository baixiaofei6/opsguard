# OpsGuard Release 清单

## 版本

- **版本号**：v0.2.1
- 日期：2026-11-25
- 定位：可回滚的 Windows 运维 CLI。v0.2.0 = v0.1.0 基础上按用户/GLM 反馈补齐证据链 + Claude Code 风格 TUI + 断网排障决策树，并**彻底移除本地模型**（用户决定）。

## 交付文件清单与 SHA256

以下哈希对本期交付文件逐一用 SHA256 计算（UTF-8 文件内容字节）。`Release-清单.md` 自身为自引用文件，故不在此表内重复列出。

| 文件（相对 `opsguard/`） | 字节数 | SHA256 |
|---|---|---|
| `README.md` | 21855 | `8de21b4a1793433db342315de3e08b413c2561f1d6d4e4dd2b00e18f86eda449` |
| `src/tui.py` | 85043 | `73fa7a1d6250a20a8961f039f9e0acf4c43dc6890e89770724e6b7a5f8a51be1` |
| `src/ai_chat.py` | 10559 | `7c989ead326c5b2930ee7e0d860e2204e84b543ad84c3721aeba1b112df95771` |
| `src/tests/test_ai_chat.py` | 13134 | `6c05d1c0aacc890daa2e0a1bcf2b95c6bcfd3f78a7dc79d3b45bd84c901f099b` |
| `src/tests/test_do_menu.py` | 6381 | `94bd08376307b9b618ab2db4672e02b3e634cfa5788750200140bd86aface772` |
| `src/suggest.py` | 4022 | `055b1247468da90ae5e387ed7ce6141419b821c7f31e075811e51bbb3f5f46df` |
| `src/opsguard.py` | 30557 | `991c3e2e56a5242c92dc96c9b6f72af2db72067e16b97c8acceda0e1320cea25` |
| `src/pricing.py` | 11771 | `9a73b9860953d8b57a3a4d4aa0b1535a1da5bc0f2ab0ad4bc00fa0cbf32c9cb1` |
| `src/keystore.py` | 19758 | `d09b6712290f5476e68ef5a888d703fef1219a4ae46453e72a5f6c2037b46e5c` |
| `src/evidence.py` | 6832 | `9b7a61c84f0ce7b01cbd6b1bba9d4381592f86fe5d3a1c186d1aaf47939c064d` |
| `src/net_rules.py` | 18839 | `2c3f7a3c09734de57c7645d2fdac23e7b2e705d1bd6ee3c0c14cae67b1a81396` |
| `src/config.py` | 2847 | `97ec9347473ee4ab1fde3675f86d3c179eed0aa67d3531d37933b3e7351f1b12` |
| `src/doctor.py` | 4122 | `b209f2bfaa3ac8e529d74ef3c023077ea33e3a29c020f6339dcdb808f339048a` |
| `src/backends/cloud.py` | 3521 | `58ba0b8ca755bc9d68d386c3db493d2a29eb12dc4118f669c0e2d81d076ccc89` |
| `src/backends/factory.py` | 3614 | `9c1a29203b46ecb3c466f7c044afd7123d1cc2ae3ff38c4da7a9f9122199b583` |
| `src/backends/base.py` | 2649 | `51cf98d1c4ac5118df74aaabce63821a57580bfab036c63aef588041a21757d3` |
| `src/adapters/system.py` | 4870 | `800494100d71225024efd8f1e5512dda416e3fbe6863cf5a3c0c88bec99d6725` |
| `src/opsguard.config.json` | 225 | `e88107b6cc5a5b82539e49faa6f7f9e7fdcf2663600c2b5aba0e8b24845067fa` |
| `TROUBLESHOOTING.md` | 7580 | `501e67ff85ec7cfbc57601b9442c9c41cf67a1b4e9c2e8ee051fba57166819b1` |
| `回滚失败预案.md` | 3072 | `25c999cfc47779ad64eaf2b252076ebf426202e07838767a94ae679169f977fc` |
| `运营建议.md` | 3677 | `841edfb3028b40f6303cc343ec17156676bedd1c1069ef0edde9e4579670f11f` |
| `拦截矩阵.md` | 3576 | `e5fa9fc44b22105ac215eed9f363193b4aa793fd2a2d7308741bdcb4030751e8` |
| `mcp/README.md` | 1747 | `d29173189e4e1d5d82e288838fe2bdc49fd46303bcb87bdc7d5693296a10e864` |
| `mcp/interface-draft.md` | 1953 | `89420c2c0826b8d18f07428548eb34b8acfce0a07e322640531e6e84dd04ca95` |
| `启动-OpsGuard.bat` | 312 | `3cd3cf022bd52d6c01e8f1371f2a58bda3680ad2aa50dd277f2702f2baef0542` |

> 上述哈希为本次交付写入时刻的真实值。若之后改动任一文件，须重算对应哈希并更新本表（校验命令见下）。

## 既有阶段文件（未改动，沿用各阶段 README 记录）

本期未改动 c1/c2/c3 任何已有文件。各阶段文件清单与职责见：

- `c1/README.md`：脱敏层双栈 + `--ai` 样本演示。
- `c2/README.md`：诊断闭环 + AST 三态。
- `c3/README.md`：安全执行器 + 隔离夹具。
- 根级：`TASK.md`、`TASK-正式版.md`、`TASK-证据链与交互增强.md`、`方案设计-阶段B.md`、`视觉规范-执行版.md`、`DECISION-*.md`、`design-preview-phase*.html`、`baseline*.json`、`baseline-scan.ps1`、`adversarial-verify.py`、`ps-ast-verify.ps1`、`测试记录.md`、`正式版测试记录.md`、`对抗测试用例清单.md`、`调研报告-阶段A.md`、`监督剖析笔记.md`。

## 变更说明（v0.2.0）

- **移除本地模型**（用户 2026-11-23 决定）：删 `backends/local.py` + `install_local.py` + `install-local` 子命令；降级链改 cloud→rules；配置/ doctor / 测试同步清理。断网排障改用完备决策树。
- **断网排障决策树**（`src/net_rules.py`）：16 类根因全覆盖，每卡可诊断/给修复/可回滚；2 类走 AST 安全门自动修，14 类 manual_only 只给指引不自动执行（不绕过宪法）；知识库补充命中复用 lan-ops-scan 语料。
- **证据链命令**（`src/evidence.py`）：`selftest`（拦截矩阵数字）、`astcheck`（10 条混淆变体 deny）、`sanitize`（脱敏 payload + 映射）、`hashdemo`（回滚三方哈希 before→after→restored + 显式断言，隔离夹具）。
- **Claude Code 风格 TUI**（`src/tui.py` 增强）：折叠/展开（≈Ctrl+O）、`/config` 设置面板、`/mode manual|readonly` 权限模式、确认菜单默认 N、命令历史；明确不提供 auto/bypass（安全红线）。宇宙主题 logo 保留。
- **深度测试轮（本轮）修复**：确认菜单 y/N/d/a 做成真状态机（原先按 y 被当命令报 invalid choice）；菜单告知按 DRY-RUN/LIVE 分别如实显示（DRY 明说不真改不备份）；`d` 键显示真 diff 内容而非键名；readonly 补拦 `/config set`；删除假开关 `color` 与文档里已作废的 `--no-color`/`--quiet`/`--dry-run`/`install-local` 描述；新增 TUI 回归、边界参数、TUI 错误处理测试（test_cli.py 26/26）；`audit --last` 负数、`netdiag --top` 非正数边界已加校验；TUI 未知命令拦截 + stderr 捕获，不污染终端。
- **API Key 管理 + 模型自由选择（本轮新增，用户要求）**：新增 `src/keystore.py` 本地 Key 仓库——`key add/list/remove` 增/删/改、`model use/add/remove` 自由选模型，CLI 与 TUI（`/key` `/model`）双入口；Key 只存本机 `.keystore/keys.json`（权限收紧仅当前用户可读、非加密、已进 `.gitignore`），显示只露头4尾4，任何输出/日志/测试/清单都无明文；api_base/key/model 三者同一出处防错配，环境变量 `OPSGUARD_API_KEY` 作旧行为兜底；只读模式拦增删/选择。新增 test_keystore.py(27)+CLI key/model(5)+TUI key/model(4)，共 90 项 src 单测全绿。
- **官方地址/模型自动配置（本轮新增，用户 m04538「光给 key 还要填地址」）**：按各家官方文档更正预设——DeepSeek base=`https://api.deepseek.com`、模型 `deepseek-flash`/`deepseek-v4-pro`（旧 `deepseek-chat`/`deepseek-reasoner` 已停用），新增百炼/Kimi(kimi-k3.1-pro)/智谱(glm-4.6)；`keystore.py` 加 `guess_provider()`（只认 sk-proj-/智谱 id.secret，普通 sk- 歧义不强猜）+ `fetch_models()` 只访问用户选定那家 /models（Codex CLI 做法）、失败只回 reason 不泄 Key；CLI 加 `key suggest`、`key add` 省略 provider、`model fetch`；TUI 加编号服务商菜单 + `/key fetch`。**用户只需填 Key、点一下服务商，地址与模型自动配好**。单测 90→95。
- **真实出网轮（本轮新增）**：用户提供智谱 Key 实测——`model fetch` 从官方 `/models` 拉到 13 个模型，`explain --backend cloud` 完整链路（脱敏→出网→回填→返回）成功。抓修第 12 个真 bug：`opsguard.py` 的 `BackendError` 与 cloud/factory 的 `from base import` 双重导入成两个类，导致异常捕获失效、traceback 漏终端；统一为 `from base import BackendError` 后 429 输出简洁、退出码 5、无栈泄漏。zhipu 预设免费模型 `glm-4-flash` 排首位（收费模型报 429/余额不足）。新增 TestBackendErrorCaught 2 测试 + 预设断言 1 项，单测 95→97，明文 Key 零泄漏。
- **两项目接入 --ai（用户 m04253 授权写回任务内文件）**：lan-ops-scan 加 `ai_ops.py` + `lanops.py --ai/--ai-backend`；windeploy-kit 加 `modules/AI-Commentary.psm1` + `WinDeploy.ps1 -AI/-AIBackend`；零依赖桥调 OpsGuard `explain`，找不到/无 Key 优雅降级并在报告注明。两项目 README 补用法。
- **官方计费标注 + 只填 Key 全自动选模型（本轮新增，用户 m05105「选厂商发 Key 后自动获取模型标注每个模型计费再让我选」）**：新增 `src/pricing.py` 官方核价表——DeepSeek（真查价：flash 输入¥1/命中¥0.02/输出¥4，高峰×2；v4-pro ¥4.5/¥0.15/¥13.5）、智谱（GLM-5.3 ¥8/¥2/¥28、5.3-flash ¥0.8/¥0.23/¥2.8 等，免费档 glm-4-flash/4.7-flash）标具体单价；Kimi/百炼/OpenAI 数字页未逐条抓到的如实标"价格以官网为准"+来源链接，绝不编造。核心关键事实：`/models` 只返回模型 id、不返回价格，所以计费只能来自官方价格页人工整理（每条带 source+verified 日期）。`model fetch` 拉模型后自动 annotate 计费、CLI/TUI 双入口编号选一个设为执行模型；`/key add` 存 Key 后自动拉模型+标计费+编号选（TUI 默认开，`OPSGUARD_KEY_AUTOFETCH=0` 可关；CLI `key add --fetch-models`）；新增 `model prices [服务商]` 查本地核价表（不出网）；未核到单价的模型在选择时明确提醒会用余额。新增 test_pricing.py 15 项（核价表来源真实性/真数字/unknown 不编造/annotate join/边界/TUI 编号选择）+ CLI prices 2 + TUI pricing 3，单测 97→118。抓修：test_backends 未隔离 keystore 被本机真 Key 污染（已改临时空 keystore）；TUI key add 自动拉取在测试里用假 Key 真出网（已加隔离开关）。
- **方向键选择菜单 + 双击启动（本轮新增，用户 m05404「希望操作也像 Claude 命令行一样，新起一个窗口，用上下方向键切换」）**：新增 `src/tui.py` 的 `select_menu()`——真终端原始按键（Windows msvcrt `\xe0P/H`、Unix termios `\x1b[A/B`）上下高亮切换、Enter 确认、Esc 取消、原地重绘；服务商菜单 `/key add` 与模型菜单 `/model fetch` 都改用它（带计费标注，选哪个即执行模型）。非交互/管道保留数字序号输入兼容。新增 `启动-OpsGuard.bat` 双击新开独立窗口启动 TUI（自动选系统 Python 或 DSH 内置 Python）。新增 test_pricing.py TestSelectMenuArrows 6 项（含 Windows msvcrt 字节翻译 mock，不碰真 tty），单测 118→124。
- **打字可见性修复（本轮新增，用户「打字的时候显示不了已打文字」）**：strings 深挖真 claude.exe v2.1.319 抓到 TUI 是 React/Ink(`Button/Input/Select/Link`)+Node readline(`cursorTo/clearScreenDown/kRefreshLine`)——即靠 ANSI 光标控制 + 每次立即刷新整行。对照定位两个根因：①`tui.py` 所有 writer 只 `write` 不 `flush`，打字内容卡在 Python 缓冲看不到；②Windows conhost 默认不开 VT，`\x1b[2K`/`\x1b[NG` 光标控制失效。修：加统一 `_out()`(write+flush)、`_enable_windows_vt()`(ctypes SetConsoleMode 开 ENABLE_VIRTUAL_TERMINAL_PROCESSING)、LineEditor 加 `vt` 参数——有 VT 用 ANSI 原地重绘、无 VT 降级成 `\r`+空格覆盖+可见 `│` 光标标记（打字每步可见）、全局 `ANSI_OK`/`render()` 让无 VT 真控制台走纯文本不留 `\x1b` 乱码。新增 TestVisibleTyping 4 项（_out 必 flush/无VT逐字标记/有VT用ANSI/非tty逐字可见），单测 147→151。诚实边界：真键盘端到端点击未做，靠注入键流+mock 覆盖。
- **Minecraft 式淡字联想（本轮新增，用户「输入指令字母时像我的世界输入指令一样根据字母淡字联想，回车自动选择当前联想指令，每打一个字母联想一个相关联的指令」）**：新增零依赖 `src/suggest.py`——按命令词库(与 build_parser 对齐)+历史频率，每输入一个字母联想最相关命令/子命令/参数，返回要补到光标后的剩余串；`LineEditor` 加 `autosuggest` 开关与 ghost 淡字渲染——有 VT 用灰色 ANSI(`GHOST`)淡字显示在光标后 + 光标停在联想前，无 VT 降级成 `(联想:xxx)` 文字提示，非 tty 保留确定性 readline(不开联想兼容)。**第一次 Enter 采纳补全、再按一次 Enter 才执行**；完整命令/无联想时回车直接执行；光标不在行尾不联想；确认态(y/N/d/a)自动关闭联想避免吃掉选择。新增 test_suggest.py 11 项(前缀/完整命令不联/斜杠/子命令参数/历史加权/无网络/TUI采纳/光标中间不联/关闭联想)+ 验收脚本加 CLI autosuggest 冒烟项，单测 151→162、检查 25→26。
- **主命令行编辑（本轮新增，用户「主命令也改吧，直接逆向 Claude 命令行看看它怎么做到的」）**：`src/tui.py` 新增 `LineEditor` + 扩展语义键流，`run_repl()` 主循环从 `input()` 换成行编辑器。真终端支持 ←→ 移光标、↑↓/Ctrl+P/N 翻历史、Home/End、Ctrl+A/E/K/U/W、Ctrl+Y、Alt+B/F、Ctrl+R 反搜、Esc 清空、回车提交；非 tty 保留 readline 兼容。键位依据官方文档 interactive-mode 的 Text editing / Command history 表（本机 claude.exe 是 Rust/Bun 打包，strings 只抓到确认文案、抓不到键位表，如实标注）。新增 `src/tests/test_line_editor.py` 22 项（纯注入按键流），单测 124→147。诚实边界：只做单行编辑，未做多行内光标分支/全屏导航/补全菜单；Windows 真键盘用 mock 覆盖、未做端到端真按键。
- **/do 核心功能菜单（本轮新增，用户「我没看到这项目能干的功能，本身要有的功能也做的一样」）**：`src/tui.py` 加 `_do_menu_items()`/`_handle_do()`，输入 `/do` 弹方向键菜单，列出 12 项核心能力（报错排障/断网排障/报告解读/带回滚修复/AST 拦截/脱敏/回滚哈希/拦截矩阵/环境自检/后端/审计/--ai 补丁），每项一句人话说明 + 内置样例/隔离夹具 argv，选中即一键试跑真实效果并复用折叠/确认/tag。菜单绝无 `--live`/`--apply`，不碰真系统；`/help` 与启动横幅加入口。新增 test_do_menu.py 7 项（12 项逐项真跑退出码符合预期无 Traceback/无 live-apply/TUI 选择/Esc/无效序号/help），单测 162→169、检查 26→27。
- **AI 排障对话 + 确认模式**（2026-11-24）：新增 `src/ai_chat.py`（运维专家角色锁定 / 修复建议解析 fail-closed / 多轮对话 / AST 判定 / manual-auto 决策 / 夹具执行）；CLI `ai` 子命令、TUI `/ai` 对话态 + `/aimode manual|auto` 切换（持久化+状态栏显示）、`/do` 加 ★AI 首项并修"报告解读写死 rules"的 bug；两模式都保留 AST/备份/哈希/回滚，auto 只免逐次问。新增 25 项单测，总 195。
- **v0.2.1 无 Key 提示 + 发布清洁**（2026-11-25，本轮）：AI 对话需要云端 Key，没配时 CLI/TUI（含 `/do` 首项）明确提示先 `/key add`，不再静默降级成离线规则让人以为 AI 没用；显式 `--backend rules` 是故意用离线规则、不拦。新增 `ai_chat.has_ai_key()`/`NO_KEY_HINT`。单测 195→202。发布前清洁核查：真 Key 从未进任何发布物（git 历史/exe/zip/源码 grep 真 Key 特征 0 命中），交付文档里一处脱敏片段也清掉；发布物里 `sk-*` 全是测脱敏用的明显假字符串。exe 重打（launcher 补 ai_chat 依赖、版本号 v021→v022 触发重新释放），zip 升 v0.2.1。
- **doctor 升级**：加脱敏映射目录可写 + 黄金测试集可跑两项自检；backend 加人话降级说明，doctor 显示 Key 来源与当前模型（不明文）。
- **README 全套**：定位/快速开始/三场景/断网决策树/证据链命令/退出码/安全机制/FAQ（含"为什么不做本地模型"卖点）/非目标。
- v0.1.0 历史：C1 脱敏层 + C2 诊断/AST + C3 安全执行器 + C4 MCP 占位 + D 文档；各阶段经父代理独立复核并修复真 bug（详见 `测试记录.md`）。

## 便携使用方式（零依赖）

整个 `opsguard/` 目录整体拷贝到目标机器即可，Python 3.8+ 标准库 + PowerShell 5.1 自带模块，不装任何包、不改系统。

- 运行演示与测试命令见 `README.md` 快速开始一节。
- PowerShell 5.1 为唯一运行时基准；若目标机是 PS7 + Pester 5，需显式 `Import-Module Pester -RequiredVersion 3.4.0` 才能跑测试。
- 所有 PowerShell 脚本带 UTF-8 BOM；复制时保持文件原样，勿用会吞 BOM 的编辑器回存。

## 校验命令

```powershell
# 复核某个交付文件的哈希（示例：README.md）
Get-FileHash -Algorithm SHA256 "C:/Users/Administrator/.dsh/im/opsguard/README.md"
# 或用 Python 标准库
python -c "import hashlib;print(hashlib.sha256(open(r'C:/Users/Administrator/.dsh/im/opsguard/README.md','rb').read()).hexdigest())"
```
