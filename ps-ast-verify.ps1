$ErrorActionPreference = 'Stop'
Import-Module 'C:/Users/Administrator/.dsh/im/opsguard/c2/AstGuard.psm1' -Force

$cases = @(
    @{ cmd = 'Get-Service -Name Spooler';                                  exp = 'allow_readonly' },
    @{ cmd = 'Set-Service -Name Spooler -Status Running';                  exp = 'require_confirm' },
    @{ cmd = 'Get-Service -Name';                                          exp = 'deny' },
    @{ cmd = 'Set-Service -Name -Status Running';                          exp = 'deny' },
    @{ cmd = 'Get-Service -Name X; Set-Service -Name X -Status Running';   exp = 'require_confirm' },
    @{ cmd = 'Set-Service -Name X -Status Running; Get-Service -Name X';   exp = 'require_confirm' },
    @{ cmd = 'Get-Service -Stat Running';                                  exp = 'deny' },
    @{ cmd = 'Remove-Service X';                                           exp = 'deny' }
)

$bad = 0
foreach ($c in $cases) {
    $r = Assert-OGCommand -Command $c.cmd
    $got = $r.verdict
    $ok = ($got -eq $c.exp)
    if (-not $ok) { $bad++ }
    $mark = if ($ok) { 'OK  ' } else { 'FAIL' }
    Write-Output ("{0} [{1}/{2}] {3}" -f $mark, $c.exp, $got, $c.cmd)
}
Write-Output ("=== ps-ast adversarial: {0}/{1} pass, {2} FAIL ===" -f ($cases.Count - $bad), $cases.Count, $bad)
