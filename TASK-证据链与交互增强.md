# OpsGuard 增强规格：Claude Code 风格交互 + 证据链补全

> 地位：正式版 v1.0.0 之后的增量规格。基于用户 2026-11-23 m03353 的三大诉求统合而成。
> 本文件是"统归提示词"——把 Claude Code 真实交互机制、GLM 缺口清单、GLM 反本地模型论证三股意见，由 DSH(lead) 裁决后写成可执行规格。
> 老规格 `TASK-正式版.md` 继续有效；本文件只做**增量与修订**，冲突处以本文件为准。

---

## 0. 来源真实性声明（用户极重视，先讲清楚）

> 用户裁决优先级：**m03384（彻底砍本地模型+强化排障规则）> 之前所有"本地混合/下载安装"需求**。本文档已按此裁决修订，§3 为最终版。

1. **Claude Code 交互机制**：来自两条真实来源，不是凭印象——
   - 本机真实二进制 `C:\Users\Administrator\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`（v2.1.319，344807072 字节）用 `strings` 抓到的真实文案与键位；
   - Claude Code 官方文档 `code.claude.com/docs/zh-CN/settings-reference.md`（verbose / viewMode / defaultMode）、`interactive-mode`、`permission-modes`。
   - REA 反编译本轮走不通（`rea-agents 6.8.0 doctor`：node 24.14.1 超范围、Ghidra 12.2 不接受、JDK 21 不满足、MCP config_drift）→ 如实说明，改用 strings + 文档取证，未假装跑通 REA。
2. **GLM 两份意见**：由用户转述（缺口清单 P0/P1/P2 + 反本地模型论证）。用户要求"统合润色提示词接着做"，即由 DSH 裁决采纳范围，不是无脑照抄。
3. 用户审美沿用已固化偏好：自然克制、不中二、不 ASCII 大字、不故作老成/年轻。

---

## 1. 交互层：Claude Code 风格 TUI（用户第一诉求：现在的交互命令不喜欢）

### 1.1 抓到的真实机制（要做进 OpsGuard）

| Claude Code 机制 | 真实细节 | OpsGuard 落地方式 |
|---|---|---|
| **可展开收起（核心）** | `verbose=false` 默认把工具调用折叠成一行摘要；`Ctrl+O` 切紧凑/详细；`viewMode`=default/verbose/focus；折叠处提示"ctrl+o to expand" | 长输出（诊断详情/脱敏映射/diff 全文/哈希明细/审计条目）默认折叠为一行摘要（`✓ diagnose 3 findings · /expand 展开`）；`/verbose` 或 `/expand` 切换全局展开；摘要行带展开提示。因当前 REPL 走 stdin `input()`，无法捕获真 Ctrl+O 组合键，用命令式触发并在帮助里标注"（= Claude Code Ctrl+O）"，诚实不装 |
| **设置** | `/config` 面板 + `settings.json`；Verbose output / viewMode / defaultMode 可持久化 | `/config` 显示当前 backend / verbose / no-color / 权限模式 / 配置路径；`/config set <键> <值>` 写回 `opsguard.config.json` |
| **选项/确认菜单** | 多选菜单 Space 切换 / Enter 确认 / a 全选 / n 全不选 / i 反选 / l 切换最新；文案 "Yes, and don't ask again" / "No, and tell … what to do differently" | 确认门显示结构化菜单：`[y] 确认执行 / [N] 取消(默认) / [d] 看完整 diff / [a] 看 AST 判定理由`；默认 N、无超时自动（宪法红线不学 Claude Code 的 auto/bypass 免确认模式） |
| **权限模式** | Shift+Tab 切 manual/acceptEdits/plan/auto/bypassPermissions | OpsGuard 只保留 `manual`(每次确认) / `readonly`(只诊断不修复) 两档；**明确不提供 auto/bypass**——安全定位决定这是红线，帮助里如实说明差异 |
| **输入框提示** | 底部 composer + 右对齐状态 | 提示行 `message OpsGuard... · /help · /verbose 展开 · /config 设置`；底部状态栏 `✦ OpsGuard v1.0.0 · backend=rules · mode=manual` |
| **Emacs 键位** | Ctrl+A/E 行首尾、Ctrl+K/U 删、Up/Down 历史、Ctrl+R 搜索历史 | stdin 模式下能实现的做：Up/Down 历史（用 readline 或自维护历史）；其余在帮助里说明为新终端留口子，不假装实现 |

### 1.2 交互层验收
- 启动 `--tui` 出宇宙 logo + 三行品牌头 + 底部状态栏（已有，保留）。
- 跑 `/doctor` 默认只显示一行摘要 + 展开提示；`/verbose` 后显示完整自检表；再 `/verbose` 收回。
- `/config` 面板可读可改，改后落盘、`/config` 再读回一致。
- 确认门菜单四选项齐全、默认 N、拒绝自动批准。
- `/help` 列全命令，标注与 Claude Code 的对应关系与差异。

---

## 2. 证据链补全：GLM 缺口清单（用户第二诉求，按 P0→P1→P2）

> GLM 一句话总结准确：现在证明"产品做出来了"，正式版验收标准是"证据拿得出来"。三张身份证 = selftest 拦截矩阵数字、回滚三个哈希值、脱敏后的 payload。

### P0（不补不算正式版）
- **P0-0 install-local 裁决**：见 §3（折中，不全砍也不照旧）。
- **P0-1 selftest + 拦截矩阵数字输出**：新增 `opsguard selftest`，跑全部黄金测试（C1 unittest 14 / C2 unittest 15 / C1 Pester 10 / C2 Pester 32 / C3 Pester 20 / AST 对抗 Py18+PS8），输出**拦截矩阵表**：9 类用例各多少条、全绿数字、总耗时。这张表进 README + 作为核心交付物。
- **P0-2 回滚三方哈希完整演示**：`fix --live --confirm y --rollback` 在夹具上输出完整链路：`hash_before → hash_after → hash_restored`，显式断言 `restored==before 且 after!=before`。`rollback` 子命令同样三值齐全。
- **P0-3 AST deny 侧演示**：新增 `opsguard astcheck --demo`，喂混淆变体（iex / 反引号拼接 / `& $var` / `-enc` / `param` 缩写 / `--%` 停止解析符 / Alias 覆盖）→ 逐条输出 deny + 命中节点 + 理由，证明 fail-closed 不是只放行侧好看。

### P1（正式感关键）
- **P1-1 脱敏证据子命令**：`opsguard sanitize --demo`，输入含真实 IP/MAC/主机名的日志，输出脱敏后 payload（`IP→[IP1]`、`HOST→[HOST1]`、`MAC→[MAC1]`）+ 本地映射表位置；断言出网 payload 不含原始值。
- **P1-2 audit 完整记录展示**：`audit` 输出一条完整记录字段（时间/输入摘要/AST 判定/确认结果/执行结果/备份路径）。
- **P1-3 exit code 语义修正**：GLM 指出的撞语义——现状 `1=需确认` 违背惯例。改为 `0 成功 / 2 等待确认(非失败) / 1 真错误 / 3 AST拒绝 / 4 回滚失败冻结 / 5 参数错误 / 6 后端不可用`。同步 README、TUI 标签、测试。
- **P1-4 backend 人话解释**：`effective` 旁加一句"当前将使用：rules（云端未配 Key、本地未起，已如实降级）"。
- **P1-5 README 全套**：定位/demo 截图/拦截矩阵表/非目标(Non-Goals)/脱敏局限/FAQ(含"为什么断网排障不做本地模型")/故障排查≥8 条。

### P2（锦上添花）
- **P2-1 doctor 扩展为证据链自检**：加两项——脱敏映射表目录可写、黄金测试集存在且可跑。
- **P2-2 demo 闭环脚本**：3 分钟逐秒脚本 + 输出渲染（截图/GIF 若条件允许），最终验收物。

### P3（用户第一诉求里的交互，与上面并行）
- 见 §1 全部。

---

## 3. 本地模型裁决（用户 m03384 最终决定：彻底砍掉 + 强化排障规则）

### 决定（覆盖此前所有"本地模型"需求）
用户 2026-11-23 明确选择："**我选择彻底砍掉本地模型，还是把断网后的排障规则写的完善一点吧，尽量能处理会遇到的所有问题**。"

这条覆盖了：
- ask_user_question custom 里的"云端+本地混合/预留本地接口/官方链接自动下载安装"；
- `TASK-正式版.md` 第 5 行追加需求、§0 表格"本地模型对接官方下载"一行、§3.2 LocalBackend、§3.8 本地模型安装器、§4 非目标例外注脚、§5 验收里的安装器测试；
- GLM 反本地模型论证（用户采纳其结论：断网排障=封闭域决策树，不需要本地模型）。

### 执行
1. **删除本地模型相关代码**：`src/backends/local.py`、`src/install_local.py` 从交付与 Release 清单移除；`src/backends/factory.py` 降级链改为 `cloud → rules`（去掉 local），`effective_backend` 去掉 local 分支；`src/opsguard.py` 删 `install-local` 子命令与 `cmd_install_local`；`backend` 子命令 choices 去掉 local；配置 `opsguard.config.json` 删 `local_base/local_dir/llamacpp_release_repo/local_model_repo`；doctor 删本地模型检查项。对应测试同步删改，全绿为准。
2. **backend 只剩两档**：`cloud`（有 OPSGUARD_API_KEY 走 OpenAI 兼容出网，payload 必过脱敏）与 `rules`（离线规则模式，如实标注）。`auto`=有 Key 走 cloud，否则 rules。
3. **README FAQ 把"为什么不做本地模型"写成卖点**（采纳 GLM 论证）：断网排障是封闭域决策树——快、确定、零依赖；"别的 AI Agent 断网就瘫，OpsGuard 的离线诊断不依赖任何模型，因为排障要的是确定性，不是概率"。
4. **把省下的力气全砸在断网排障规则完备性上**（用户核心新要求）：见 §3A。

### 3A. 断网排障规则完备化（新增核心任务）
目标：决策树覆盖断网遇到的**所有**常见问题，每张卡片做到"可诊断 + 可给出确定性修复命令 + 可回滚 + 可验证"。

必须覆盖的根因清单（至少）：
1. DNS 服务器指向不可达 / 配置错误
2. DNS Client 服务停止
3. 网卡被禁用（Get-NetAdapter Status=Disabled）
4. 网卡无有效 IP（169.254 自动私有地址 / DHCP 失败）
5. 默认网关缺失或错误
6. Winsock 目录损坏（netsh winsock reset）
7. TCP/IP 协议栈异常（netsh int ip reset）
8. DNS 缓存污染（ipconfig /flushdns）
9. hosts 文件被改动/劫持
10. 静态 IP 冲突 / 与 DHCP 冲突
11. 代理设置残留（WinINET/环境变量/WINHTTP 代理指向失效地址）
12. 防火墙/安全软件拦截（出站规则误配）
13. 网卡驱动异常（设备管理器感叹号）
14. IPv6 优先导致解析异常（IPv6 无连通性但优先）
15. 网线/链路层断开（Link Speed=0 / Media Disconnected）

每条规则卡片结构：`{id, symptom_pattern, probe_commands[], root_cause, confidence, evidence_checks[], fix_command, rollback_command, ast_tier, plain_english, next_if_fail}`。
- `probe_commands` 只读诊断命令；`fix_command` 必须过 AST 白名单且可回滚；禁止清单里的动作（删服务/格式化/关安全软件）永远不产出。
- 输出给用户的诊断报告含：根因 + 置信度 + 证据链 + 建议动作 + 失败后的下一步（呼应 GLM 方案 1"把决策树包装出智能感"）。
- 知识库检索（GLM 方案 2）：沿用现有 lan-ops-scan 巡检语料做关键词/特征匹配，零依赖，作为规则卡的补充覆盖长尾症状。
- 测试：每类根因至少一条样例证据 → 正确命中；对抗样本（混淆变体）不得绕过 AST；全部 mock/夹具，不碰真系统。

> 一句话：**本地模型彻底砍掉；断网排障决策树做厚做全——15 类根因全覆盖、每张卡可诊断可修复可回滚，用确定性换掉概率。**

---

## 4. 不变的红线（全程）
- 构建/测试不碰真系统/任务外文件（默认工作区 WinDeploy-Kit 159 文件 / lan-ops-scan 116 文件 + 3 脚本零改动）；真实网卡 DNS/服务保持原样；测试用隔离夹具。
- 安全资产不降级：AST 三态+fail-closed+多命令取最严、脱敏层、备份→执行→三方哈希→回滚→冻结、默认 N 人工确认、禁止清单硬拒。
- 零第三方运行时依赖；Python3.8+ / PS5.1 基准；PS 模块 ASCII-only。
- 验收 ≥5 遍、每遍找并修 bug、再连跑 2 遍全绿；护栏 ZERO；Release 哈希同步。

---

## 5. 实施顺序
统合提示词(本文件) → 交互层 §1 → P0 → P1 → P2 → 全量验收 → 交付。
每完成一段同步 Release-清单.md 哈希、跑 verify-formal.py 回归；新视觉/新冲突走 DECISION-*，不静默拍板。
