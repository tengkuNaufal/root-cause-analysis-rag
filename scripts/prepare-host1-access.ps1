# Run as Administrator on Windows Host 1. No credentials or personal addresses are stored here.
# Installs OpenSSH/Tailscale, restricts SSH to LAN/tailnet, and disables AC sleep.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in an Administrator PowerShell window.'
}
$repo = Split-Path $PSScriptRoot -Parent
$local = Join-Path $repo 'private\host1-access'
New-Item -ItemType Directory -Force -Path $local | Out-Null
Start-Transcript -Path (Join-Path $local 'setup.log') -Append
try {
    powercfg /query SCHEME_CURRENT SUB_SLEEP | Out-File (Join-Path $local 'power-before.txt')
    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
    $capability = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
    if ($capability.State -ne 'Installed') {
        Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' | Out-Null
    }
    Set-Service sshd -StartupType Automatic
    Start-Service sshd
    # Replace the installer's broad inbound rule with an explicit LAN/tailnet scope.
    Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue | Disable-NetFirewallRule
    $rule = 'RCA-Host1-SSH'
    if (-not (Get-NetFirewallRule -Name $rule -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -Name $rule -DisplayName 'RCA Host 1 SSH (LAN and Tailscale)' `
            -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 -Profile Any `
            -RemoteAddress 'LocalSubnet','100.64.0.0/10' | Out-Null
    }
    $tailscale = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (-not (Test-Path -LiteralPath $tailscale)) {
        winget install --id Tailscale.Tailscale --exact --source winget --silent `
            --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -ne 0) { throw "Tailscale install failed: $LASTEXITCODE" }
    }
    Get-Service sshd,Tailscale | Select-Object Name,Status,StartType | ConvertTo-Json | Set-Content (Join-Path $local 'services.json')
    'completed' | Set-Content (Join-Path $local 'setup-state.txt')
} catch {
    $_ | Out-String | Set-Content (Join-Path $local 'setup-error.txt')
    throw
} finally {
    Stop-Transcript
}
