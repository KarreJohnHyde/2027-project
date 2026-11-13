<#
.SYNOPSIS
  Starts (or stops) a MedTwin stack: FastAPI backend, durable-queue worker and Vite.

.DESCRIPTION
  -Mode qa (default) starts an ISOLATED stack for browser verification: a fresh
  SQLite database, upload store and AES-256-GCM storage key in a scratch directory
  outside the repository, a generated QA login (written only to that directory),
  worker-mode job execution, backend on 8010 and a freshly built Vite preview on 8453.
  It never touches the development database, so no patient record can appear in QA
  screenshots.

  -Mode dev starts the backend on 8000 against backend/medtwin.db and Vite on 8443
  (inline job execution), reusing verified MedTwin services already listening.
  Reused services are not stopped by -Stop.

  State (PIDs, URLs, credentials path) is written to <StateDir>/stack.json; run with
  -Stop to terminate the processes recorded there.

.EXAMPLE
  npm run dev:full
  npm run dev:stop
#>
param(
    [ValidateSet("qa", "dev")][string]$Mode = "qa",
    [string]$StateDir = (Join-Path $env:TEMP "medtwin-qa"),
    [int]$BackendPort = 0,
    [int]$WebPort = 0,
    [switch]$Fresh,
    [switch]$NoWorker,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$StateDir = [System.IO.Path]::GetFullPath($StateDir)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$StateFile = Join-Path $StateDir "stack.json"

function Get-OwnedProcess($State, [string]$Name) {
    # A recorded PID is ours only while the very process this script started is alive. Windows reuses PIDs, so after
    # a restart the same number can belong to an unrelated program, which must never be stopped or mistaken for us.
    $processId = $State.pids.$Name
    if (-not $processId) { return $null }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    try { $startTime = $process.StartTime } catch { return $null }
    $recorded = $null
    if ($State.PSObject.Properties.Name -contains "process_started" -and $State.process_started.$Name) {
        $recorded = [datetime]$State.process_started.$Name
    }
    if ($recorded) {
        if ([math]::Abs(($startTime - $recorded).TotalSeconds) -gt 2) { return $null }
    } elseif ($process.ProcessName -ne "cmd" -or $startTime -gt ([datetime]$State.started_at).AddSeconds(5)) {
        # Records written before process_started existed: our launcher is cmd.exe, started before the record.
        return $null
    }
    return $process
}

function Stop-Stack {
    if (-not (Test-Path $StateFile)) { Write-Host "No stack state at $StateFile."; return }
    $state = Get-Content $StateFile -Raw | ConvertFrom-Json
    foreach ($name in "web", "worker", "backend") {
        $processId = $state.pids.$name
        if (-not $processId) { continue }
        if (-not (Get-OwnedProcess $state $name)) {
            Write-Host "Skipped $name PID $processId (no longer running, or the number now belongs to another program)."
            continue
        }
        # taskkill /T also ends child processes (npm -> node, uvicorn reloader).
        $previousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
        $taskkillExit = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorPreference
        if ($taskkillExit -ne 0) { throw "Could not stop $name process tree (PID $processId; taskkill exit $taskkillExit)." }
        Write-Host "Stopped $name (PID $processId)."
    }
    Remove-Item -LiteralPath $StateFile
}

function Test-PortFree([int]$Port) {
    # The CIM listener inventory can be unavailable or incomplete on a managed
    # workstation. Probe the same loopback address the services actually use.
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.ConnectAsync("127.0.0.1", $Port)
        # Windows can take about two seconds to report a refused loopback
        # connection. A shorter deadline incorrectly labels a free port busy.
        if (-not $connection.Wait(5000)) { throw "Timed out probing loopback port $Port; could not determine whether it is available." }
        return -not $client.Connected
    } catch {
        $cause = $_.Exception.GetBaseException()
        if ($cause -is [System.Net.Sockets.SocketException] -and $cause.SocketErrorCode -eq [System.Net.Sockets.SocketError]::ConnectionRefused) {
            return $true
        }
        throw
    } finally { $client.Dispose() }
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 90) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -lt 500) { return $true }
        } catch { Start-Sleep -Milliseconds 750 }
    }
    return $false
}

function Start-Logged([string]$WorkingDirectory, [string]$CommandLine, [string]$Log) {
    # cmd.exe performs the redirection, so Start-Process can use ShellExecute: the child
    # inherits no handles from this console and the caller is not held open by it.
    $process = Start-Process -FilePath "cmd.exe" -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden `
        -ArgumentList "/d", "/c", "`"$CommandLine > `"$Log`" 2>&1`""
    return $process.Id
}

function New-Secret([int]$Bytes = 24) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

if ($Stop) { Stop-Stack; exit 0 }
if (Test-Path $StateFile) {
    $previous = Get-Content $StateFile -Raw | ConvertFrom-Json
    $alive = @("web", "worker", "backend" | Where-Object { Get-OwnedProcess $previous $_ })
    if ($alive.Count -gt 0) { throw "A stack is already running ($($alive -join ', ')), recorded in $StateFile. Run with -Stop first." }
    Write-Host "Discarding the stack record from $($previous.started_at): its processes have ended (for example after a restart)."
    Remove-Item -LiteralPath $StateFile
}
if (-not (Test-Path $Python)) { throw "Python environment not found at $Python." }

if ($Mode -eq "qa") {
    if (-not $BackendPort) { $BackendPort = 8010 }
    if (-not $WebPort) { $WebPort = 8453 }
    if ($Fresh -and (Test-Path $StateDir)) {
        $resolvedStateDir = [System.IO.Path]::GetFullPath($StateDir).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
        foreach ($item in "medtwin-qa.db", "medtwin-qa.db-wal", "medtwin-qa.db-shm", "uploads") {
            $target = Join-Path $StateDir $item
            if (-not (Test-Path $target)) { continue }
            $resolvedTarget = [System.IO.Path]::GetFullPath($target)
            if (-not $resolvedTarget.StartsWith($resolvedStateDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove QA state outside $resolvedStateDir`: $resolvedTarget"
            }
            # SQLite can hold its file handle for a fraction of a second after the
            # process tree exits. Retry this narrowly scoped cleanup instead of making
            # an immediate stop-and-fresh cycle flaky.
            for ($attempt = 1; $attempt -le 20; $attempt++) {
                try {
                    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force -ErrorAction Stop
                    break
                } catch {
                    if ($attempt -eq 20) { throw }
                    Start-Sleep -Milliseconds 250
                }
            }
        }
    }
    New-Item -ItemType Directory -Force -Path $StateDir, (Join-Path $StateDir "uploads"), (Join-Path $StateDir "logs") | Out-Null
    $keyFile = Join-Path $StateDir "storage.key"
    if (-not (Test-Path $keyFile)) {
        & $Python -c "import json, sys; sys.path.insert(0, sys.argv[2]); from app.services.storage_crypto import generate_key; json.dump({'keys': {'qa-1': generate_key()}, 'active': 'qa-1'}, open(sys.argv[1], 'w'))" $keyFile (Join-Path $Root "backend")
        if ($LASTEXITCODE -ne 0) { throw "Could not generate the storage key." }
    }
    $credentialFile = Join-Path $StateDir "qa-credentials.json"
    if (-not (Test-Path $credentialFile)) {
        @{ username = "qa_reviewer"; password = (New-Secret); email = "qa_reviewer@example.invalid" } | ConvertTo-Json | Set-Content -Encoding utf8 $credentialFile
    }
    $credentials = Get-Content $credentialFile -Raw | ConvertFrom-Json
    $environment = @{
        ENVIRONMENT = "development"; DATABASE_URL = "sqlite:///" + (Join-Path $StateDir "medtwin-qa.db").Replace("\", "/")
        UPLOAD_DIR = (Join-Path $StateDir "uploads"); MEDTWIN_STORAGE_ENCRYPTION = "required"; MEDTWIN_STORAGE_KEY_FILE = $keyFile
        MEDTWIN_JOB_EXECUTION = $(if ($NoWorker) { "inline" } else { "worker" }); MEDTWIN_PROJECT_ROOT = $Root
        DEV_SEED_ENABLED = "true"; DEV_SEED_USERNAME = $credentials.username; DEV_SEED_PASSWORD = $credentials.password
        DEV_SEED_EMAIL = $credentials.email; DEV_SEED_FULL_NAME = "QA Reviewer (synthetic account)"; DEV_SEED_ROLE = "clinician"
        DEV_SEED_CASE_ENABLED = "true"; CORS_ORIGINS = "http://127.0.0.1:$WebPort,http://localhost:$WebPort"; RATE_LIMIT_ENABLED = "false"
    }
} else {
    if (-not $BackendPort) { $BackendPort = 8000 }
    if (-not $WebPort) { $WebPort = 8443 }
    $credentialFile = $null
    $environment = @{ ENVIRONMENT = "development"; MEDTWIN_PROJECT_ROOT = $Root; MEDTWIN_JOB_EXECUTION = "inline" }
    $NoWorker = $true
    # Optional, untracked local settings for this workstation (.cache is ignored by git), for example
    # {"open_workspace_account": "10"}: no sign-in, every browser opens the workspace as that registered account.
    $localSettings = Join-Path $StateDir "settings.json"
    if (Test-Path $localSettings) {
        $settings = Get-Content $localSettings -Raw | ConvertFrom-Json
        if ($settings.open_workspace_account) {
            $environment.MEDTWIN_OPEN_WORKSPACE_ACCOUNT = [string]$settings.open_workspace_account
            Write-Host "Open workspace: no sign-in; every browser opens as registered account $($settings.open_workspace_account) and every case is shared."
        }
    }
}

$reuseBackend = $false
$reuseWeb = $false
if ($BackendPort -eq $WebPort) { throw "Backend and frontend need different ports." }
foreach ($port in $BackendPort, $WebPort) {
    if (Test-PortFree $port) { continue }
    if ($Mode -ne "dev") { throw "Port $port is already in use; choose another port for the isolated QA stack." }
    if ($port -eq $BackendPort) {
        try {
            $identity = Invoke-RestMethod -Uri "http://127.0.0.1:$port/" -TimeoutSec 5
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5
            if ($identity.framework -notlike "MedTwin*" -or $identity.api_prefix -ne "/api/v1" -or $health.status -ne "HEALTHY") {
                throw "Not a healthy MedTwin backend."
            }
        } catch { throw "Port $port is occupied and could not be verified as the MedTwin backend. Choose another backend port." }
        $reuseBackend = $true
        Write-Host "Reusing MedTwin backend on $port."
    } else {
        # The existing wrapper checks both the project identity and optimized React.
        # Since this port is occupied, it verifies/reuses it without launching Vite.
        & node (Join-Path $Root "scripts/start-vite.mjs") --host 127.0.0.1 --port $port
        if ($LASTEXITCODE -ne 0) { throw "Could not reuse the frontend on $port." }
        $reuseWeb = $true
    }
}

$logs = Join-Path $StateDir "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$saved = @{}
foreach ($key in $environment.Keys) { $saved[$key] = [Environment]::GetEnvironmentVariable($key); [Environment]::SetEnvironmentVariable($key, $environment[$key]) }
$pids = @{}
try {
    if (-not $reuseBackend) {
        $pids.backend = Start-Logged $Root "`"$Python`" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $BackendPort" (Join-Path $logs "backend.log")
    }
    if (-not (Wait-Http "http://127.0.0.1:$BackendPort/health")) { throw "Backend did not become healthy; see $logs\backend.log." }

    if (-not $NoWorker) {
        $pids.worker = Start-Logged (Join-Path $Root "backend") "`"$Python`" -m app.worker --poll-seconds 1" (Join-Path $logs "worker.log")
    }

    foreach ($key in "PORT", "FIGMA_DEV_SERVER_HOST", "MEDTWIN_BACKEND_URL") {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key)
    }
    [Environment]::SetEnvironmentVariable("PORT", "$WebPort")
    [Environment]::SetEnvironmentVariable("FIGMA_DEV_SERVER_HOST", "127.0.0.1")
    [Environment]::SetEnvironmentVariable("MEDTWIN_BACKEND_URL", "http://127.0.0.1:$BackendPort")
    $webCommand = "npx vite --port $WebPort --strictPort"
    if ($Mode -eq "qa") {
        # Browser acceptance needs a deterministic current bundle, not HMR. A
        # production build plus Vite preview avoids cold dev-server transforms
        # while retaining the same local API/WebSocket proxy.
        Push-Location $Root
        try {
            $previousErrorPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            & npm.cmd run -s build *> (Join-Path $logs "build.log")
            $buildExit = $LASTEXITCODE
            $ErrorActionPreference = $previousErrorPreference
        } finally {
            $ErrorActionPreference = $previousErrorPreference
            Pop-Location
        }
        if ($buildExit -ne 0) { throw "Frontend QA build failed; see $logs\build.log." }
        $webCommand = "npx vite preview --port $WebPort --strictPort"
    }
    if (-not $reuseWeb) { $pids.web = Start-Logged $Root $webCommand (Join-Path $logs "web.log") }
    # A cold Tailwind/Vite dependency optimization can exceed 90 seconds on this
    # Windows workspace even though the process is healthy; allow the UI its own
    # startup budget while retaining the same active HTTP readiness check.
    if (-not (Wait-Http "http://127.0.0.1:$WebPort/" 180)) { throw "Vite did not start; see $logs\web.log." }
    if (-not (Wait-Http "http://127.0.0.1:$WebPort/api/v1/system/health")) { throw "The Vite proxy cannot reach the backend." }
} catch {
    foreach ($processId in $pids.Values) { & taskkill.exe /PID $processId /T /F 2>$null | Out-Null }
    throw
} finally {
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key]) }
}

$processStarted = @{}
foreach ($name in @($pids.Keys)) {
    $process = Get-Process -Id $pids[$name] -ErrorAction SilentlyContinue
    if ($process) { $processStarted[$name] = $process.StartTime.ToString("o") }
}
$state = [ordered]@{
    mode = $Mode; started_at = (Get-Date).ToString("o"); pids = $pids; process_started = $processStarted
    backend_url = "http://127.0.0.1:$BackendPort"; web_url = "http://127.0.0.1:$WebPort"
    credentials_file = $credentialFile; logs = $logs; job_execution = $environment.MEDTWIN_JOB_EXECUTION
    reused_backend = $reuseBackend; reused_web = $reuseWeb
}
$state | ConvertTo-Json | Set-Content -Encoding utf8 $StateFile
Write-Host "MedTwin $Mode stack is up: web $($state.web_url), API $($state.backend_url) (jobs: $($state.job_execution))."
if ($credentialFile) { Write-Host "QA credentials: $credentialFile" }
