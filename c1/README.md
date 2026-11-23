# OpsGuard C1 —— P0 脱敏层 + --ai 自包含样本演示

> **定位**：阶段 C1 自包含实现。全部文件仅在 `C:/Users/Administrator/.dsh/im/opsguard/` 内新建；**演示用样本报告；改造既有项目需用户另行授权**。未进入 C2/C3/C4。
> 环境基准：Python 3.12.10（要求 3.8+，纯标准库）/ PowerShell 5.1.26100.8655 / Pester 3.4.0（系统自带）。零第三方运行时与测试依赖。

## 1. 新建文件清单

| 文件 | 作用 |
|---|---|
| `c1/redact.py` | Python 脱敏层：RFC1918 边界感知 + 八位组校验、MAC 三变体、主机名精确表、确定性映射、回填、出网唯一出口 |
| `c1/Redact.psm1` | PowerShell 5.1 脱敏模块：与 Python 版同规则、同占位符语义 |
| `c1/test_redact.py` | Python unittest 黄金测试（14 项） |
| `c1/Redact.Tests.ps1` | Pester 3.4 管道语法测试（10 项，无 Pester 5 语法） |
| `c1/demo_ai.py` | --ai 样本演示：样本→证据→脱敏→本地规则→回填→追加 section，输出到 out/ |
| `samples/sample-lan-ops-scan.html` | 浅色样本（模拟 lan-ops-scan），标明「样本，非真实项目产物」 |
| `samples/sample-windeploy.html` | 深色样本（模拟 WinDeploy），标明「样本，非真实项目产物」 |
| `c1/out/sample-lan-ops-scan.ai.html` | 演示产物：浅色样本副本 + 追加段落（原件未动） |
| `c1/out/sample-windeploy.ai.html` | 演示产物：深色样本副本 + 追加段落（原件未动） |
| `c1/README.md` | 本文件 |

## 2. 测试命令与结果（全绿）

### Python（标准库 unittest，**无 pytest**）
```powershell
python -m unittest discover -s "C:/Users/Administrator/.dsh/im/opsguard/c1" -p "test_*.py" -v
# 结果：Ran 14 tests ... OK  → 14 passed / 0 failed
```
覆盖：RFC1918 三段命中与公网/越界/边界子串不误伤、八位组 0-255、MAC 三变体、主机名精确表+长度降序、替换↔回填往返 6 组（≥5，含同值多次、混合文本）、确定性映射、抓「出网 payload」断言无原始 IP/MAC/主机名、映射表仅本地、无 Key 降级、demo 全链与 samples 原件哈希不变。

### PowerShell（系统自带 Pester 3.4，**管道语法**）
```powershell
Invoke-Pester -Script "C:/Users/Administrator/.dsh/im/opsguard/c1/Redact.Tests.ps1" -PassThru
# 结果：Passed: 10 Failed: 0 Skipped: 0 → 10 passed / 0 failed
```
断言均用管道式 `$x | Should Be $true`，**未使用 Pester 5 的 `Should -Be`**；静态扫描 `Should\s+-` / `-Show` / `BeforeAll|AfterAll` 命中数 = 0。

## 3. 演示运行

```powershell
python "C:/Users/Administrator/.dsh/im/opsguard/c1/demo_ai.py"
# 控制台输出两行「生成：...out\*.ai.html」；samples/ 原件哈希不变
```
追加段落 `<section id="opsguard-ai">`：主题自适应宿主（浅/深两套静态内联 CSS）、三栏证据卡（三态判定 / unified diff + 一句人话 / 回滚证据）、颜色 + 中文方括号标签双通道（no-color 语义不丢）、屏幕三栏打印单栏、零依赖。两段 out/ 产物仅用于演示；`--with-key` 显式报错，不静默包装成离线 AI。

## 4. 脱敏覆盖与局限（如实标注）

- **覆盖**：RFC1918 三段（10/8、172.16/12、192.168/16，边界感知 + 八位组 0-255）；MAC 冒号/横杠/Cisco 点分；调用方提供的**精确主机名表**（禁泛正则，按长度降序）。
- **未覆盖（MVP 范围外）**：公网 IP、敏感文件路径、用户名、IPv6、无分隔符 12 位连续 MAC（易误伤版本号）、云元数据地址、FQDN 自动发现。有此类需求需扩展规则并补测试。
- **出网纪律**：真实出网只发送 `prepare_outbound()` / `Get-RedactionPayload` 返回的已脱敏文本；映射表只留本地 `mapping_table()` / `Get-RedactionMap`，回填后才展示，绝不随请求出网。无 Key 模式不出网、脱敏不触发、不报错。

## 5. 边界声明

- 全部产物为样本演示；**改造既有 WinDeploy-Kit / lan-ops-scan 需用户另行授权**，本 C1 未触碰默认工作区任何既有项目文件。
- C1 到此为止，未进入 C2（诊断闭环）、C3（安全执行器）、C4（MCP 薄层）。
