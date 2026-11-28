# Menjalankan cek lab dan fault di host utama dari laptop lewat SSH.
# Alamat dan user host utama diisi di laptop\config.ps1 (salin dari config.example.ps1).
#
#   .\laptop\lab.ps1 doctor
#   .\laptop\lab.ps1 reach
#   .\laptop\lab.ps1 check
#   .\laptop\lab.ps1 faults F01 F16
#   .\laptop\lab.ps1 faults --all
#   .\laptop\lab.ps1 status            # progres benchmark di data/host2/bench
#   .\laptop\lab.ps1 status 12         # detail baris jadwal 12 (atau last)
#   .\laptop\lab.ps1 watch             # nonton tmux benchmark read-only, keluar pakai Ctrl+B lalu D
#   .\laptop\lab.ps1 demo F01 graph_rag
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('doctor', 'reach', 'check', 'faults', 'status', 'watch', 'demo')]
    [string]$Action,
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

function Show-Item([string]$Name, [bool]$Ok, [string]$Detail) {
    $mark = if ($Ok) { '[OK]  ' } else { '[--]  ' }
    Write-Host ($mark + $Name.PadRight(22) + $Detail)
}

function Invoke-Doctor {
    $os = Get-CimInstance Win32_OperatingSystem
    Show-Item 'Windows' $true ("$($os.Caption) build $($os.BuildNumber)")

    foreach ($tool in 'ssh', 'ssh-keygen', 'git', 'python', 'wsl') {
        $cmd = Get-Command $tool -ErrorAction SilentlyContinue
        if ($cmd) { Show-Item $tool $true $cmd.Source } else { Show-Item $tool $false 'tidak ditemukan di PATH' }
    }

    $key = Join-Path $env:USERPROFILE '.ssh\id_ed25519.pub'
    if (Test-Path $key) { Show-Item 'SSH key' $true $key }
    else { Show-Item 'SSH key' $false 'belum ada (opsional: ssh-keygen -t ed25519)' }

    if (Get-Command wsl -ErrorAction SilentlyContinue) {
        $distros = (wsl -l -q) -replace "`0", '' | Where-Object { $_.Trim() -ne '' }
        if ($distros) { Show-Item 'Distro WSL' $true (($distros | ForEach-Object { $_.Trim() }) -join ', ') }
        else { Show-Item 'Distro WSL' $false 'belum ada distro (tidak wajib untuk SSH)' }
    }

    $cfg = Join-Path $PSScriptRoot 'config.ps1'
    Show-Item 'laptop\config.ps1' (Test-Path $cfg) $(if (Test-Path $cfg) { 'ada' } else { 'belum dibuat' })
}

if ($Action -eq 'doctor') { Invoke-Doctor; exit 0 }

$cfgPath = Join-Path $PSScriptRoot 'config.ps1'
if (-not (Test-Path $cfgPath)) {
    Write-Host 'laptop\config.ps1 belum ada. Salin config.example.ps1 menjadi config.ps1 lalu isi nilainya.'
    exit 2
}
. $cfgPath

if ($Action -eq 'reach') {
    $r = Test-NetConnection -ComputerName $HostIp -Port 22 -WarningAction SilentlyContinue
    Show-Item "TCP $HostIp`:22" $r.TcpTestSucceeded $(if ($r.TcpTestSucceeded) { 'terbuka' } else { 'tidak terjangkau' })
    exit $(if ($r.TcpTestSucceeded) { 0 } else { 1 })
}

$remoteArgs = @{
    'check'  = 'python3 scripts/check_lab.py --lab rca'
    'faults' = 'python3 scripts/fault_runner.py run'
    'status' = 'python3 scripts/bench_status.py data/host2/bench'
    'watch'  = 'tmux attach -r -t bench'
    'demo'   = 'bash scripts/demo.sh'
}
# Membatasi argumen per aksi karena string ini dieksekusi di host utama.
$allowed = @{
    'check'  = @{ Pattern = '^$'; Max = 0 }
    'faults' = @{ Pattern = '^(F\d{2}|--all)$'; Max = 30 }
    'status' = @{ Pattern = '^(\d{1,3}|last)$'; Max = 1 }
    'watch'  = @{ Pattern = '^$'; Max = 0 }
    'demo'   = @{ Pattern = '^(F\d{2}|zero_shot|text_rag|graph_rag)$'; Max = 2 }
}
if (($Action -eq 'faults' -or $Action -eq 'demo') -and -not $Rest) {
    Write-Host 'Sebutkan ID fault, misalnya F01 (faults juga bisa --all).'
    exit 2
}
if ($Rest.Count -gt $allowed[$Action].Max) {
    Write-Host "Argumen kebanyakan untuk $Action"
    exit 2
}
foreach ($arg in $Rest) {
    if ($arg -notmatch $allowed[$Action].Pattern) {
        Write-Host "Argumen tidak dikenal: $arg"
        exit 2
    }
}
$remote = "wsl -d $Distro -u $LinuxUser --cd `"$RepoPath`" -- " + $remoteArgs[$Action]
if ($Action -eq 'status' -and $Rest) { $remote += ' --show ' + $Rest[0] }
elseif ($Rest) { $remote += ' ' + ($Rest -join ' ') }

# Memakai -t buat aksi interaktif: demo minta token, watch nampilin tmux.
$sshArgs = @()
if ($Action -eq 'demo' -or $Action -eq 'watch') { $sshArgs += '-t' }

$sw = [Diagnostics.Stopwatch]::StartNew()
ssh @sshArgs "$WinUser@$HostIp" $remote
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ('[laptop] perintah selesai dalam {0:N1} s, exit code {1}' -f $sw.Elapsed.TotalSeconds, $code)
exit $code
