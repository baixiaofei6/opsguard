# OpsGuard

可回滚的 Windows 运维 CLI + Claude Code 风格交互界面。敢真改 DNS / 服务 / 注册表 / 文件，因为每一步都有语法树校验、预演、人工确认、备份、回滚和哈希验证。

## 直接下载（推荐，打开即用）

到 [Releases](https://github.com/baixiaofei6/opsguard/releases) 下载最新版 `OpsGuard-v0.2.1-win64.zip`，解压后双击 `OpsGuard.exe` 即可。首次运行自动把程序释放到 `%LOCALAPPDATA%\OpsGuard\`，**不用装 Python、不用装任何第三方库**（Windows 10/11 自带 PowerShell 5.1）。也可以只下载独立的 `OpsGuard.exe`。

## 进来第一件事：输入 `/do`

方向键列出 OpsGuard 本身能干的 12 件事，选一个回车就先用内置样例跑真实效果给你看：报错排障、断网排障（16 类根因决策树）、报告解读、带回滚修复、AST 拦截演示、脱敏证据、回滚哈希闭环、拦截矩阵、环境自检、后端状态、审计日志、生成 --ai 补丁。菜单里绝无真改开关，绝不碰你的系统。

## AI 排障对话 `/ai`（需要 API Key）

像 Claude Code 那样连续对话解决服务器/电脑问题（系统/网络/服务/注册表/DNS/网卡）。**没配 Key 会明确提示先 `/key add`，不会偷偷降级**——配置好后地址/模型自动带出，还能从官方 `/models` 拉实时模型并标出计费让你选。修复建议先过 AST 白名单，再按你选的确认模式（`/aimode manual` 每次问 / `auto` 免问）处理；TUI 里默认只在夹具演练，不真改系统。

## 能做什么

- **三场景**：报错排障 / 断网排障（16 类根因）/ 带回滚修复，一条内核。
- **可证明安全**：AST 语法树白名单 + 禁止清单 + 脱敏 → 预演 → 显式确认 → 备份 → 执行 → 三方哈希 → 失败冻结。修改默认演练、默认 N。
- **日志脱敏**：内网 IP/MAC/主机名占位符替换，本地存映射表，出网不带内网信息。
- **可插拔 AI 后端**：OpenAI 兼容云端（配 Key 走）/ 离线规则（无 Key 降级）。没有本地模型——断网排障靠完备的决策树，不是模型猜测。

## 安全边界（说清楚）

- 修改默认 DRY-RUN、默认 N；真改系统只能命令行 `ai --execute --live --confirm y`。
- 白名单外的危险命令（编码命令、下载执行链、动态拼接、别名等）AST 层硬拒，`auto` 也不放行。
- `auto` 只是「免逐次问」，AST/备份/哈希/回滚一道不少。没有绕过安全的 bypass 模式。
- Key 只存本机 `.keystore`，权限仅当前用户，不进日志 / 输出 / 交付物。

## 从源码运行（可选）

```powershell
python src/opsguard.py --tui     # 交互界面
python src/opsguard.py /do       # 从源码看功能菜单（CLI 用 do）
python src/opsguard.py doctor    # 环境自检
```

Python 3.8+ 纯标准库 + PowerShell 5.1 自带模块，零第三方运行时依赖。详见仓库内 `README.md`。

## 许可

MIT。
