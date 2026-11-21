# Client Host 2: 16 replay berurutan, satu baris JSONL per percobaan.
# Kompatibel dengan Windows PowerShell 5.1 dan PowerShell 7.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [uri]$BaseUrl,
    [string]$OutputFile,
    [ValidateRange(1, 3600)]
    [int]$TimeoutSec = 600
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

function Require([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Has-Field($Object, [string]$Name) {
    return $null -ne $Object -and $null -ne $Object.PSObject.Properties[$Name]
}

function Read-Json([string]$Text) {
    return ConvertFrom-Json -InputObject $Text -ErrorAction Stop
}

function Get-Response([string]$Method, [string]$Path, [string]$Body = '') {
    $uri = [uri]::new($script:Endpoint, $Path)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $reply = $null
    $content = $null
    try {
        if ($Method -eq 'POST') {
            $content = [Net.Http.StringContent]::new($Body, [Text.Encoding]::UTF8, 'application/json')
            $reply = $script:Client.PostAsync($uri, $content).GetAwaiter().GetResult()
        } else {
            $reply = $script:Client.GetAsync($uri).GetAwaiter().GetResult()
        }
        $text = $reply.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $clock.Stop()
        return [pscustomobject]@{
            Status = [int]$reply.StatusCode
            Text = $text
            Seconds = $clock.Elapsed.TotalSeconds
        }
    } finally {
        $clock.Stop()
        if ($null -ne $reply) { $reply.Dispose() }
        if ($null -ne $content) { $content.Dispose() }
    }
}

function Check-Reply($Value, $Scenario) {
    Require ($Value.api_version -ceq '1.0') 'Unsupported API version.'
    Require ($Value.scenario_id -ceq $Scenario.id) 'Scenario ID differs from request.'
    Require ($Value.profile -ceq $Scenario.profile) 'Profile differs from catalog.'
    Require (($Value.synthetic -is [bool]) -and ($Value.synthetic -eq $Scenario.synthetic)) 'Invalid synthetic flag.'
    Require ($Value.mode -ceq 'replay') 'Response must be replay-only.'
    Require ($Value.run_id -cmatch '^[0-9a-f]{32}$') 'Invalid run ID.'
    Require ($Value.status -cin @('hypothesis', 'abstain')) 'Invalid domain status.'
    Require (($Value.execution_allowed -is [bool]) -and -not $Value.execution_allowed) 'Execution must remain disabled.'
    Require (($Value.diagnosis_allowed -is [bool]) -and -not $Value.diagnosis_allowed) 'Diagnosis authorization must remain disabled.'
    Require ((Has-Field $Value 'proposed_patch') -and @($Value.proposed_patch).Count -eq 0) 'Response contains a patch.'
    Require (($Value.result.execution_allowed -is [bool]) -and -not $Value.result.execution_allowed) 'Result enables execution.'
    Require ((Has-Field $Value.result 'proposed_patch') -and @($Value.result.proposed_patch).Count -eq 0) 'Result contains a patch.'
    Require ($Value.result.status -ceq $Value.status) 'Inconsistent result status.'
    if ($Value.status -ceq 'hypothesis') {
        Require ($Value.phase -cin @('baseline', 'fault', 'recovered', 'undetermined')) 'Invalid phase.'
    } else {
        Require ($null -eq $Value.phase) 'Abstention must not expose an accepted phase.'
    }
    Require ($Value.timing.unit -ceq 'seconds') 'Invalid server timing unit.'
    foreach ($name in @('agent_seconds', 'total_seconds')) {
        $number = $Value.timing.$name
        Require (($number -is [ValueType]) -and ($number -isnot [bool])) 'Server timing must be numeric.'
        Require (-not [double]::IsNaN($number) -and -not [double]::IsInfinity($number) -and $number -ge 0) 'Invalid server timing.'
    }
    Require ($Value.timing.agent_seconds -le $Value.timing.total_seconds) 'Server timing order is invalid.'
    $ids = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    Require (Has-Field $Value 'evidence') 'Evidence list is missing.'
    foreach ($item in @($Value.evidence)) {
        Require ($item.id -cmatch '^[A-Za-z0-9_-]{1,32}$') 'Invalid evidence ID.'
        Require ($ids.Add([string]$item.id)) 'Duplicate evidence ID.'
        Require ($item.sha256 -cmatch '^[0-9a-f]{64}$') 'Invalid source hash.'
        Require ($item.source_id -ceq ('sha256:' + $item.sha256)) 'Inconsistent source ID.'
        $expected = '/v1/runs/' + $Value.run_id + '/evidence/' + $item.id
        Require ($item.url -ceq $expected) 'Evidence URL is not the expected relative API route.'
    }
    Require (Has-Field $Value 'citations') 'Citation list is missing.'
    foreach ($claim in @($Value.citations)) {
        $claimIds = @($claim.evidence_ids)
        $claimUrls = @($claim.evidence_urls)
        Require ($claimIds.Count -eq $claimUrls.Count) 'Citation URL count differs from evidence IDs.'
        for ($index = 0; $index -lt $claimIds.Count; $index++) {
            $id = $claimIds[$index]
            Require ($ids.Contains([string]$id)) 'Citation refers to unknown evidence.'
            Require ($claimUrls[$index] -ceq ('/v1/runs/' + $Value.run_id + '/evidence/' + $id)) 'Citation URL differs from its evidence ID.'
        }
    }
}

$writer = $null
$Client = $null
$handler = $null
$exitCode = 1
try {
    Require ($BaseUrl.IsAbsoluteUri -and $BaseUrl.Scheme -in @('http', 'https')) 'BaseUrl must be an absolute HTTP(S) URL.'
    Require (-not $BaseUrl.UserInfo -and -not $BaseUrl.Query -and -not $BaseUrl.Fragment) 'BaseUrl must not contain credentials, query or fragment.'
    Require ($BaseUrl.AbsolutePath -eq '/') 'BaseUrl must be the server root URL.'
    $Endpoint = [uri]::new($BaseUrl.GetLeftPart([UriPartial]::Authority) + '/')
    if (-not $OutputFile) {
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
        $suffix = [guid]::NewGuid().ToString('N').Substring(0, 8)
        $OutputFile = Join-Path $PSScriptRoot "../data/host2/replay-$stamp-$suffix.jsonl"
    }
    $OutputFile = [IO.Path]::GetFullPath($OutputFile)
    Require ([IO.Path]::GetExtension($OutputFile) -ieq '.jsonl') 'OutputFile must use the .jsonl extension.'
    Require (-not (Test-Path -LiteralPath $OutputFile)) 'Output file already exists; choose a new file.'

    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseProxy = $false
    $Client = [Net.Http.HttpClient]::new($handler)
    $Client.Timeout = [TimeSpan]::FromSeconds($TimeoutSec)
    $Client.DefaultRequestHeaders.Accept.ParseAdd('application/json')
    $healthReply = Get-Response 'GET' '/health'
    Require ($healthReply.Status -eq 200) 'Health request failed.'
    $health = Read-Json $healthReply.Text
    Require ($health.status -ceq 'ok' -and $health.mode -ceq 'replay_only') 'Server is not a replay API.'
    Require (($health.execution_allowed -is [bool]) -and -not $health.execution_allowed) 'Server enables execution.'
    Require (($health.active -is [bool]) -and -not $health.active) 'Server is busy; wait until active is false.'
    $catalogReply = Get-Response 'GET' '/v1/scenarios'
    Require ($catalogReply.Status -eq 200) 'Catalog request failed.'
    $catalog = Read-Json $catalogReply.Text
    Require ($catalog.api_version -ceq '1.0' -and $catalog.mode -ceq 'replay_only') 'Invalid catalog metadata.'
    Require (($catalog.execution_allowed -is [bool]) -and -not $catalog.execution_allowed) 'Catalog enables execution.'
    $scenarios = @($catalog.scenarios)
    Require ($scenarios.Count -eq 16) 'Expected exactly 16 registered scenarios.'
    $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($scenario in $scenarios) {
        Require ($scenario.id -cmatch '^[a-z0-9._-]{1,80}$') 'Invalid catalog scenario ID.'
        Require ($seen.Add([string]$scenario.id)) 'Duplicate catalog scenario ID.'
        Require ($scenario.profile -cin @('temporal-bound', 'mtu-observation')) 'Unknown scenario profile.'
        Require ($scenario.synthetic -is [bool]) 'Invalid catalog synthetic flag.'
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $catalogHash = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($catalogReply.Text)))).Replace('-', '').ToLowerInvariant()
    } finally { $sha.Dispose() }

    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($OutputFile)) | Out-Null
    $stream = [IO.FileStream]::new($OutputFile, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
    $writer.NewLine = "`n"
    $writer.AutoFlush = $true
    $sessionId = [guid]::NewGuid().ToString('N')
    $sequence = 0
    $exitCode = 0
    Write-Host "Running 16 scenarios sequentially. Output: $OutputFile"
    foreach ($scenario in $scenarios) {
        $sequence++
        $totalClock = [Diagnostics.Stopwatch]::StartNew()
        $fetchClock = [Diagnostics.Stopwatch]::new()
        $record = [ordered]@{
            schema_version = 'host2-replay-client-1.0'
            client_session_id = $sessionId
            sequence = $sequence
            scenario_count = 16
            scenario_id = $scenario.id
            profile = $scenario.profile
            synthetic = $scenario.synthetic
            base_url = $Endpoint.AbsoluteUri.TrimEnd('/')
            catalog_sha256 = $catalogHash
            started_at_utc = [DateTime]::UtcNow.ToString('o')
            finished_at_utc = $null
            first_request_in_session = ($sequence -eq 1)
            http_status = $null
            outcome = 'transport_error'
            client_checks_passed = $false
            server_completion_unknown = $false
            client_response_seconds = $null
            server_agent_seconds = $null
            server_total_seconds = $null
            evidence_fetch_seconds = 0.0
            client_total_seconds = $null
            evidence_verified = 0
            response = $null
            raw_error_body = $null
            error = $null
        }
        $stage = 'post'
        try {
            $body = @{ scenario_id = $scenario.id } | ConvertTo-Json -Compress
            $reply = Get-Response 'POST' '/v1/replays' $body
            $record.http_status = $reply.Status
            $record.client_response_seconds = $reply.Seconds
            $stage = 'decode'
            if ($reply.Status -ne 201) {
                $record.outcome = 'http_error'
                $record.raw_error_body = $reply.Text
                throw "HTTP $($reply.Status); replay not accepted as a completed result."
            }
            $record.outcome = 'invalid_json'
            $record.raw_error_body = $reply.Text
            $value = Read-Json $reply.Text
            $record.response = $value
            $record.raw_error_body = $null
            $record.outcome = 'validation_error'
            Check-Reply $value $scenario
            $record.server_agent_seconds = $value.timing.agent_seconds
            $record.server_total_seconds = $value.timing.total_seconds
            $stage = 'evidence'
            $record.outcome = 'evidence_error'
            $fetchClock.Start()
            foreach ($item in @($value.evidence)) {
                $fetch = Get-Response 'GET' $item.url
                Require ($fetch.Status -eq 200) "Evidence fetch failed: HTTP $($fetch.Status)."
                $actual = Read-Json $fetch.Text
                foreach ($field in @('id', 'kind', 'source_id', 'sha256', 'locator', 'content', 'url')) {
                    Require ((Has-Field $actual $field) -and ($actual.$field -ceq $item.$field)) "Evidence differs at field $field."
                }
                $record.evidence_verified++
            }
            $fetchClock.Stop()
            $record.outcome = $(if ($value.status -ceq 'abstain') { 'abstain' } else { 'success' })
            $record.client_checks_passed = $true
        } catch {
            $exception = $_.Exception.GetBaseException()
            $record.error = [ordered]@{ stage = $stage; type = $exception.GetType().Name; message = $exception.Message }
            if ($stage -eq 'post') {
                $record.server_completion_unknown = $true
                $record.client_response_seconds = $totalClock.Elapsed.TotalSeconds
                $record.outcome = 'transport_error'
                $exitCode = 2
            } else { $exitCode = 1 }
        } finally {
            $fetchClock.Stop()
            $totalClock.Stop()
            $record.evidence_fetch_seconds = $fetchClock.Elapsed.TotalSeconds
            $record.client_total_seconds = $totalClock.Elapsed.TotalSeconds
            $record.finished_at_utc = [DateTime]::UtcNow.ToString('o')
        }
        $writer.WriteLine(($record | ConvertTo-Json -Depth 100 -Compress))
        $writer.BaseStream.Flush($true)
        Write-Host ('[{0}/16] {1}: {2}, POST {3:N3}s' -f $sequence, $scenario.id, $record.outcome, $record.client_response_seconds)
        if (-not $record.client_checks_passed) {
            Write-Warning 'Stopped after saving the failed attempt. No retry was sent; inspect the JSONL and server health before starting a new session.'
            break
        }
    }
    if ($exitCode -eq 0) { Write-Host 'Completed: 16 responses and their evidence verified. Abstention is a valid domain result.' }
} catch {
    Write-Warning ('Client stopped: ' + $_.Exception.GetBaseException().Message)
    $exitCode = 1
} finally {
    if ($null -ne $writer) { $writer.Dispose() }
    if ($null -ne $Client) { $Client.Dispose() }
    if ($null -ne $handler) { $handler.Dispose() }
}
exit $exitCode
