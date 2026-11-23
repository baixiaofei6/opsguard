# OpsGuard 护栏基线扫描：记录任务外文件状态，交付时对比证明零改动
# 只读扫描，不修改任何文件；输出 JSON 基线到 opsguard/baseline.json
param([string]$OutFile = "C:\Users\Administrator\.dsh\im\opsguard\baseline.json")
$ErrorActionPreference = 'SilentlyContinue'

function Get-TreeState {
    param([string]$Root)
    if (-not (Test-Path $Root)) { return @{ path = $Root; exists = $false; files = @() } }
    $files = @()
    Get-ChildItem -LiteralPath $Root -Recurse -File -Force | Where-Object {
        ($_.FullName -notmatch '\\__pycache__\\') -and ($_.Extension -ne '.pyc')
    } | ForEach-Object {
        try {
            $files += [pscustomobject]@{
                rel  = $_.FullName.Substring($Root.Length).TrimStart('\','/')
                len  = $_.Length
                sha  = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.Substring(0,16)
                mtime = $_.LastWriteTimeUtc.ToString('o')
            }
        } catch {}
    }
    return @{ path = $Root; exists = $true; count = $files.Count; files = @($files) }
}

# Build the CJK path from code points so the script itself stays pure ASCII
# (PowerShell 5.1 reads BOM-less .ps1 as ANSI/GBK and would garble literal CJK).
$docDir = 'E:\' + [char]0x6587 + [char]0x6863 + '\deepseek-harness\default-workspace\'
$targets = @(
    ($docDir + 'windeploy-kit'),
    ($docDir + 'lan-ops-scan'),
    'C:\Users\Administrator\.dsh\im\balance-remind.ps1',
    'C:\Users\Administrator\.dsh\im\usage-report.ps1',
    'C:\Users\Administrator\.dsh\im\monitor_sessions.js'
)

$result = [ordered]@{
    scannedAt = (Get-Date).ToUniversalTime().ToString('o')
    note = 'OpsGuard outside-task baseline; rerun at delivery into baseline-final.json and diff'
    targets = @()
}
foreach ($t in $targets) { $result.targets += (Get-TreeState -Root $t) }

$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding UTF8
Write-Output "BASELINE written: $OutFile"
foreach ($t in $result.targets) { Write-Output ("  {0} : exists={1} files={2}" -f $t.path, $t.exists, $t.count) }
