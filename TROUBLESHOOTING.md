# OpsGuard TROUBLESHOOTING

> 范围：常见故障 + 症状 + 处置。素材来自 c1/c2/c3/README.md、测试记录.md、DECISION-*-RESOLVED.md 与已知坑。8 条为下限，本文列 11 条。
>
> 已知问题（本期未改，按边界约束仅记录）：根级 `baseline-scan.ps1` 含中文注释但文件无 UTF-8 BOM，在 PowerShell 5.1 下有乱码风险（见第 1 条）；`ps-ast-verify.ps1` 同样无 BOM，但其内容为纯 ASCII，实测无影响。两者均为既有文件，本期未改动。

## 1. PowerShell 5.1 下中文注释乱码 / ParserError

- **症状**：导入 `.psm1` 或运行 `.ps1` 时中文注释变乱码，甚至报 `ParserError`，脚本无法加载。
- **原因**：Windows PowerShell 5.1 读取无 BOM 的 UTF-8 文件时按系统 ANSI 码页解码。用编辑工具改文件后 BOM 被吞（测试记录第 2 轮就踩过：修复 C2 PowerShell 栈时 edit 丢失 BOM 致中文乱码 ParserError）。
- **处置**：保证文件首字节为 `EF BB BF`（UTF-8 with BOM）。用 `utf-8-sig` 重新写回即可恢复。本项目所有 `.ps1/.psm1` 必须带 BOM；改完用 `[System.IO.File]::ReadAllBytes($f)[0..2]` 核对首三字节。

## 2. Pester 版本不对：`Should -Be` 报“找不到参数” / `-Show` 不被识别

- **症状**：跑测试报 `A parameter cannot be found that matches parameter name 'Be'`（`Should -Be`）或 `-Show` 参数不存在。
- **原因**：PS7 常自带 Pester 5，语法与系统自带的 Pester 3.4 不兼容。本项目基准是 Pester 3.4 管道语法（`$x | Should Be $y`），不装 Pester 5（破零依赖红线）。测试记录第 1 轮复核脚本自身就误加了 Pester 5 的 `-Show None`。
- **处置**：显式加载系统版：`Import-Module Pester -RequiredVersion 3.4.0`；断言一律管道式 `$x | Should Be $y`，不用 `Should -Be` / `BeforeAll` / `-Show`。静态扫描 `Shoulds+-` 命中应为 0。

## 3. 参数缺值被误判为 allow_readonly（已修）

- **症状**：`Get-Service -Name` 这类“参数后面没有值”的残缺命令被 AST 判成只读放行——fail-closed 不完整。
- **原因**：初版只校验 cmdlet 名在白名单，没校验参数是否带值。Python 与 PowerShell 双栈都有这个问题（测试记录第 2 轮 bug 1/2）。PowerShell 初修还踩了坑：用 `CommandParameterAst.Argument -eq null` 判缺值，实测 PS5.1 下该属性恒为 null。
- **处置**：已修。Python 侧逐个检查参数后必须有值 token；PowerShell 侧改用 `CommandElements` 数组索引判断参数后是否有值元素，不依赖恒 null 的 `Argument` 属性。回归见 `对抗测试用例清单.md` A15。

## 4. 多命令拼接导致权限提升（已修）

- **症状**：`Get-Service;Set-Service` 被判成 allow_readonly，修改类命令被当只读放行——这是最严重的一条。
- **原因**：初版只取第一条命令的 tier，第一条是只读 cmdlet 就把整条语句判只读，后面的修改命令被忽略。
- **原因补充/处置**：已修。PowerShell 侧收集所有 `CommandAst` 的 tier 取最严格者（require_confirm 优先于 allow_readonly）。回归用例见 `对抗测试用例清单.md` 与 C2 README §4。

## 5. -WhatIf / dry-run 不是沙箱，别当万能药

- **症状**：以为跑了 `-WhatIf` 就“绝对没副作用”，结果发现预演并不等同隔离执行；或某些命令 `-WhatIf` 根本不起作用。
- **原因**：`SupportsShouldProcess` 并非所有 cmdlet 都实现；注册表、部分服务操作原生不支持 WhatIf。TASK 调研明确要求如实挖出这个坑，禁止把 dry-run 说成沙箱。
- **处置**：dry-run 只作为“预演 + before/expected after + diff”的证据之一，文档与口播一律写“预演，非沙箱”。真正无副作用靠 c3 的白名单目标强校验（注册表仅 `HKCU:\Software\OpsGuardTest`、文件仅 `c3/fixtures/`，越界 fail-closed）与 dry-run 无落盘测试来保证。

## 6. 公网 IP 没被脱敏

- **症状**：出网 payload 里的公网 IP（如 `8.8.8.8`）仍是明文，用户以为脱敏没生效。
- **原因**：MVP 脱敏层只覆盖 RFC1918 三段（10/8、172.16/12、192.168/16）；公网 IP、IPv6、敏感文件路径、用户名等是明确标注的 MVP 外范围（见 `c1/README.md` §4）。
- **处置**：这是已知局限，不是 bug。如实告知范围边界；确有需求时扩展规则并补测试（注意别用泛正则误伤版本号），不要把公网 IP 当已覆盖。对抗用例 B4 已断言公网 IP“不误伤”（即不替换），符合如实标注。

## 7. 无 Key 时如何运行 / 会不会报错出网

- **症状**：没配 API Key，担心 `--ai` 链路报错或偷偷出网。
- **原因**：设计上 Key 走环境变量，未配置即进入“离线规则模式”——本地规则匹配，不发起网络请求，脱敏不触发。
- **处置**：无需任何操作即可离线跑；README/口播一律写“离线规则模式”，禁止包装成“离线 AI”。`demo_ai.py --with-key` 会显式报错提示，不静默降级。有 Key 时出网 payload 必先过脱敏层。

## 8. 注册表夹具残留空父键

- **症状**：demo 结束后 `Test-Path HKCU:\Software\OpsGuardTest` 仍为 True（留下空键），不符合“夹具自删”。
- **原因**：demo_c3.ps1 初版 finally 只删子键 `DemoDns`，留下空的 `OpsGuardTest` 父键（测试记录第 3 轮抓到）。
- **处置**：已修。finally 改为：父键空（`SubKeyCount=0` 且 `ValueCount=0`）时连父键一起删。验证命令：`Test-Path HKCU:\Software\OpsGuardTest` 必须为 False。手工残留可先跑 demo 再核对，或人工 `Remove-Item`（仅限此测试键）。

## 9. baseline.json 用 utf-8 读报 JSON 解析错

- **症状**：护栏对比脚本读 `baseline.json` 报 JSON 解码错误（首行有 `\ufeff`）。
- **原因**：baseline.json 带 BOM，用 `encoding='utf-8'` 读会把 BOM 当内容（测试记录第 1 轮）。
- **处置**：改用 `encoding='utf-8-sig'` 读取。护栏对比必须 ZERO CHANGES（added/removed/changed 全 0）。

## 10. 真实 DNS / 系统服务没动，怎么证明“执行”是真的

- **症状**：观众质疑 demo 里“改 DNS 再回滚”是不是摆拍——因为真实网卡 DNS 全程没变。
- **原因**：按 `DECISION-RESOLVED.md` 隔离夹具裁决，最高安全优先于 demo 真实度，严禁触碰真实网卡 DNS/系统服务/系统目录/引导驱动。
- **处置**：如实说明“演示在隔离夹具，非生产网卡”；证据用三方哈希（`65061df9… → 39b23f7d… → 65061df9…`，判定 `rollback_verified`）+ manifest + 审计日志（`c3/fixtures/`、`c3/audit/`）+ 拦截日志证明逻辑闭环真实。演示证明的是“能力可证明安全”，不是“对生产网卡真实改动”。

## 11. MCP 层能不能直接执行修改命令 / 为什么没有 server

- **症状**：想通过 MCP 直接跑修改命令，或疑惑 `mcp/` 目录为何只有一个 README 和接口草案、没有可运行 server。
- **原因**：本期 MCP 是 P2 占位——按宪法第 2 条只保目录与接口定义，不实现执行、不阻塞 CLI 主线。MCP 设计上只暴露只读诊断 + 返回建议，执行必须回 CLI 人工确认。
- **处置**：本期按占位使用即可，不期待执行能力；需要执行走 CLI（`demo_c3.ps1` 等）的 `y/N` 确认门。占位不等于永久不实现——后续余力足够再按 `mcp/interface-draft.md` 做薄层实现，且不引入 MCP SDK（零依赖）。
