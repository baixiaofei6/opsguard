# OpsGuard C2 —— 诊断闭环 MVP（只到「展示方案」，不含执行）

> 定位：阶段 C2 自包含实现，依赖链 `诊断引擎 → 命令生成 → AST 校验器 → 权限分级`。
> 只做到展示方案：绝不执行任何命令、不接备份回滚（那是 C3）。全程零系统状态变更。
> 环境基准：Python 3.12.10（要求 3.8+，纯标准库）/ PowerShell 5.1.26100.8655 / Pester 3.4.0（系统自带）。零第三方运行时与测试依赖。
> 全部新建文件仅在 `C:/Users/Administrator/.dsh/im/opsguard/` 内；未修改 c1/ 任何文件；未触碰默认工作区任何既有项目。

## 1. 新建文件清单

| 文件 | 作用 |
|---|---|
| `c2/diagnose.py` | 诊断引擎：证据文本 + 场景类型 → 结构化结论 + 风险排序（三场景共用，内置规则表） |
| `c2/generate.py` | 命令生成：结论 + 意图 → 候选命令字符串 + 预期效果 + 一句人话 + unified diff（不执行） |
| `c2/ast_guard.py` | Python 栈 AST 安全门：保守词法/结构校验，三态 + 理由 + 命中节点，fail-closed，白名单外/危险结构/禁止清单全 deny |
| `c2/AstGuard.psm1` | PowerShell 5.1 真 AST 安全门：System.Management.Automation.Language.Parser.ParseInput + Ast.FindAll 递归遍历，零依赖，三态语义与 Python 版一致 |
| `c2/policy.py` | Python 权限分级 + 确认门（模拟）：allow 放行 / require_confirm 默认 N / deny 硬拒，永不执行 |
| `c2/Policy.psm1` | PowerShell 权限分级 + 确认门（模拟）：语义与 Python 版一致 |
| `c2/demo_c2.py` | CLI 演示：诊断→生成→AST三态→权限分级→方案展示；三态标签（颜色+中文双通道，NO_COLOR/非TTY 降级）+ 三栏证据卡；零执行 |
| `c2/test_c2.py` | Python unittest 黄金测试（15 项） |
| `c2/C2.Tests.ps1` | Pester 3.4 管道语法测试（32 项，无 Pester 5 语法） |
| `c2/README.md` | 本文件 |

## 2. 测试命令与结果（全绿）

### Python（标准库 unittest，无 pytest）
```powershell
cd "C:/Users/Administrator/.dsh/im/opsguard/c2"
python -m unittest test_c2 -v
# 结果：Ran 15 tests ... OK → 15 passed / 0 failed
```
覆盖：allow_readonly 5 例 / require_confirm 2 例 / deny 明文 4 例（三态各 ≥2，含理由与命中节点）｜调研报告全部 14 类深层绕过变体 deny｜禁止清单在用户确认(y)路径下仍拒｜确认门默认 N / 无跳过 / 仅严格 y 或 yes 确认 / executed 恒 False｜fail-closed（语法错误/空/None）｜诊断→生成→判定全链 + 风险排序。

### PowerShell（系统自带 Pester 3.4，管道语法）
```powershell
Invoke-Pester -Script "C:/Users/Administrator/.dsh/im/opsguard/c2/C2.Tests.ps1" -PassThru
# 结果：Passed: 32 Failed: 0 Skipped: 0 Total: 32
```
断言均为管道式 `$x | Should Be $y`，未使用 Pester 5 的 `Should -Be` / `-Show` / `BeforeAll`。静态检查命中数 = 0。

## 3. 演示运行（零系统变更）
```powershell
cd "C:/Users/Administrator/.dsh/im/opsguard/c2"
python demo_c2.py fix        # 或 error / inspection
# 全程只打印方案：候选命令仅作为字符串, 送 AST 分析后展示, 不 SendCommand / 不 Invoke-Expression / 不 Start-Process / 不 subprocess
```

## 4. AST 三态与绕过矩阵（Python / PowerShell 双栈同语义）

- allow_readonly（仅由白名单标记决定，禁止正则猜）：Get-NetAdapter / Get-DnsClientServerAddress / Get-Service / Get-WinEvent / ipconfig /all。
- require_confirm（白名单修改类，进确认门）：Set-Service / Set-DnsClientServerAddress。
- deny：其余一切 + 危险结构 + 禁止清单（确认门不得覆盖）+ 解析失败/语法错误（fail-closed）。

调研报告实测的深层绕过全部覆盖并 deny：
param 缩写 -Stat｜``% 停止解析符｜` `var 动态命令名｜脚本块内命令｜Alias 覆盖（gs）｜Invoke-Expression/iex｜下载执行链 Invoke-WebRequest 接管道 iex｜`EncodedCommand/`enc｜反引号转义｜字符串拼接动态命令名｜子表达式命令参数。

PowerShell 栈实现细节：ParseInput 有 ParseError 即 deny；FindAll 递归覆盖脚本块/子表达式/管道内所有 CommandAst；命令名首元素必须是 StringConstantExpressionAst（变量/括号表达式/拼接 → fail-closed deny）；白名单 cmdlet 只接受完整参数名（缩写 deny，不靠正则猜）。

## 5. 确认门语义（C2 为模拟，不执行）

- y/N，默认 N，无超时自动执行，无跳过确认开关。
- 禁止清单（删服务/格式化/删用户数据/关安全软件）在 AST 层即 deny，即使用户确认 y 也不放行。
- 所有决策 executed=False：C2 只展示方案；执行、备份、回滚、三方哈希验证属于 C3。

## 6. 边界声明

- C2 到此为止，未进入 C3（安全执行器）、C4（MCP 薄层）、D（交付）。
- 未触碰任何真实系统服务、网卡 DNS、注册表、系统目录；未安装任何包。
- 新视觉/新冲突项见 opsguard/DECISION-C2.md，交父代理转发，未静默拍板。
