# OpsGuard C3 · 安全执行器（隔离夹具版）

> 别的 AI 助手只敢建议命令，这个敢执行——因为有 AST 语法树白名单、dry-run 预演、自动备份、一键回滚，且回滚结果经过哈希验证。
>
> **隔离声明（最高优先）**：本阶段所有"变更→备份→执行→回滚→哈希验证"链路，**全部在隔离测试夹具上运行**：临时注册表键 `HKCU:\Software\OpsGuardTest\...` + `c3/fixtures/` 内临时文件 + 纯内存状态。**真实网卡/DNS/系统服务/系统目录/引导驱动全程零改动**。TASK §4 原文"真实改 DNS 再回滚"已被 `DECISION-RESOLVED.md` 隔离夹具裁决覆盖。

## 模块与职责

| 文件 | 职责 |
|---|---|
| `backup_restore.psm1` | 备份/回滚隔离夹具目标；JSON manifest；注册表 `reg export` 到 `.reg`；目标白名单强校验（越界 fail-closed） |
| `verify_hash.psm1` | 三方 SHA256 判定；判定式写死：**回滚后 = 操作前 且 操作后 ≠ 操作前**，否则回滚失败 |
| `executor.psm1` | 流水线：AST 判定 → dry-run 预演（非沙箱）→ diff → 确认门 → 备份 → 仅夹具执行 → 哈希 → 审计；修改类命令无确认无法到达执行路径 |
| `freeze.psm1` | 回滚失败 → 保留备份 → 冻结标志 → 拒绝后续一切操作 → 输出手工恢复步骤 |
| `audit.psm1` | append-only JSONL 审计：时间/输入摘要/AST 判定/确认结果/执行结果/备份路径/回滚记录，只在 `c3/audit/` |
| `demo_c3.ps1` | 隔离夹具 1:10~2:50 完整闭环演示 |
| `Golden.Tests.ps1` | Pester 3.4 黄金测试（20 项） |

复用（未修改）：`c2/AstGuard.psm1`（AST 三态判定）、`c2/Policy.psm1`（确认门语义）、`c1/redact.py`（出网脱敏，本阶段无出网故未触发）。

## 运行命令（PS5.1 唯一基准）

```powershell
cd C:/Users/Administrator/.dsh/im/opsguard/c3

# 黄金测试（系统自带 Pester 3.4，管道语法）
powershell -NoProfile -ExecutionPolicy Bypass -Command "Import-Module Pester -RequiredVersion 3.4.0; Invoke-Pester -Script ./Golden.Tests.ps1 -PassThru"

# 隔离夹具 demo（人工确认，默认 N；输入 y 才执行）
powershell -NoProfile -ExecutionPolicy Bypass -File ./demo_c3.ps1

# demo 无人值守回放（仅演示夹具内预置 y，生产执行永远要求人工确认；见 DECISION-C3.md 条目1）
powershell -NoProfile -ExecutionPolicy Bypass -File ./demo_c3.ps1 -AutoConfirm
```

## 实测结果（2026-11-23，Windows PowerShell 5.1.26100.8655 / Pester 3.4.0）

- **Pester 黄金测试**：Total 20 / Passed 20 / Failed 0。覆盖：回滚往返 3 组（注册表临时键 1 + 夹具临时文件 2，各证明"回滚后=操作前 且 操作后≠操作前"）、确认门无旁路 4 项、dry-run 无落盘 3 项、危险命令拦截 5 项、回滚失败冻结 1 项、审计 append-only 1 项、哈希判定式单元 3 项。
- **demo 实跑**：`EXIT=0`；夹具自建自删（结束后 `DemoDns` 键不存在）；冻结标志未触发（`Frozen=False`）；三方哈希 `65061df9…` → `39b23f7d…` → `65061df9…`，判定 `rollback_verified`；3 条诱导命令（删服务明文、多命令拼接变体、``-enc`` 混淆）全部 AST deny。

## 三栏证据卡（C2-D-1 拍板：第三栏 = 回滚哈希）

屏幕三栏、打印单栏。①AST 判定（三态+理由+命中节点）②unified diff（`-当前`/`+预期`+一句人话）③回滚哈希（操作前/后/回滚后 + 判定式）。

## 安全不变量

- 修改类命令 AST 判定非 `require_confirm` 不执行；禁止清单（删服务/格式化/删用户数据/关安全软件）AST 层硬拒，用户确认也不放行。
- 确认门 `y/N` 默认 N；`SkipConfirm` 开关返回拒绝、不产生旁路；无超时自动执行。
- dry-run 只读、无落盘、明确标注"预演非沙箱"。
- 备份/回滚目标白名单：注册表仅 `HKCU:\Software\OpsGuardTest`，文件仅 `c3/fixtures/`，越界一律 fail-closed。
- 回滚失败保留备份、冻结、输出手工指引，冻结期间一切操作被拒。

## 非目标（沿用 TASK §2）

GUI、批量多机、本地模型插件、MCP 自动执行修改命令、任何自动批准/跳过确认开关、Ollama/通用 RAG。

## 待父代理转发的决策

见 `DECISION-C3.md`（demo 自动回放开关、夹具自删与证据保留的边界）。本阶段无新视觉/配色冲突；三栏第三栏按 C2-D-1 已拍板执行。
