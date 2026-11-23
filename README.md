# OpsGuard

可证明安全的 Windows 运维 AI 助手。零第三方依赖（Python 标准库 + 系统 PowerShell 5.1），Claude Code 风格 TUI。

## 直接下载用（推荐）

到 [Releases](https://github.com/baixiaofei6/opsguard/releases) 下载 `OpsGuard-v0.2.0-win64.zip`，解压后双击 `OpsGuard.exe` 即可。首次运行自动释放到 `%LOCALAPPDATA%\OpsGuard\`，**不需要装 Python 或任何依赖**。进界面第一件事输入 `/do`，方向键菜单列出全部功能。

也可以单独下载 `OpsGuard.exe`（单文件，同样首次自释放）。

## 功能

- **报错排障 / 断网排障（16 类根因）/ 报告解读 / 带回滚修复** — 三场景共用一条内核。
- **可证明安全**：AST 白名单三态 + 禁止清单 + 多命令取最严；备份 → 执行 → 三方哈希 → 回滚 → 失败冻结；修改类默认演练、默认 N。
- **脱敏后出网**：内网 IP/MAC/主机名先占位符替换，本地留映射表。
- **混合 AI 后端**：云端 OpenAI 兼容 / 离线规则降级；填 Key 后自动拉官方模型列表并标注计费（价格来自各厂商官方价格页，抓不到的诚实标"以官网为准"）。
- **Claude Code 风格 TUI**：宇宙主题 logo、行编辑（←→/Home/End/Ctrl+A/E/K/U、↑↓ 历史、Ctrl+R 反搜）、方向键菜单、Minecraft 式淡字联想、`/do` 功能菜单。

## 从源码跑

```bash
python src/opsguard.py --tui
python src/opsguard.py doctor
python src/opsguard.py selftest
```

Python 3.8+，纯标准库，Windows 需 PowerShell 5.1（系统自带）。详见 [README.md](README.md)。

## 安全边界

`fix` 默认 DRY-RUN；真改系统需显式 `--live --confirm y`，双击界面刻意不提供此选项。API Key 只存本机 `.keystore/`，权限仅当前用户，界面只显示头4尾4。

MIT License.
