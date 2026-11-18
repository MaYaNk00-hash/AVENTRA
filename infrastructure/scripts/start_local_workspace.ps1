param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$workspacePath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$logPath = Join-Path $workspacePath 'validation/runtime-logs'
$logSuffix = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
New-Item -ItemType Directory -Force -Path $logPath | Out-Null

function Test-LocalPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}

function Start-AventraProcess([string]$Name, [int]$Port, [string]$Command, [string[]]$Arguments, [string]$Directory) {
    if (Test-LocalPort $Port) {
        Write-Host "$Name already has a listener on port $Port; leaving it running."
        return
    }
    $process = Start-Process -FilePath $Command -ArgumentList $Arguments -WorkingDirectory $Directory `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logPath "$Name-$logSuffix.stdout.log") `
        -RedirectStandardError (Join-Path $logPath "$Name-$logSuffix.stderr.log")
    Write-Host "Started $Name (PID $($process.Id)); logs: $logPath"
}

Start-AventraProcess -Name 'client' -Port 8100 -Command $Python -Arguments @('-m','uvicorn','prototype_client.app:app','--host','127.0.0.1','--port','8100') -Directory $workspacePath
Start-AventraProcess -Name 'backend' -Port 8000 -Command $Python -Arguments @('-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000','--reload') -Directory $workspacePath
Start-AventraProcess -Name 'frontend' -Port 3000 -Command $env:ComSpec -Arguments @('/c','npm run dev -- --port 3000') -Directory (Join-Path $workspacePath 'frontend')

foreach ($endpoint in @('http://127.0.0.1:8100/openapi.json','http://127.0.0.1:8000/api/health','http://127.0.0.1:3000')) {
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw "Service did not become ready: $endpoint. Inspect $logPath and the existing process on that port." }
    Write-Host "Ready: $endpoint"
}
Write-Host 'Open http://localhost:3000 and sign in with your backend account. Provider connectivity is verified by an actual request, not by this startup check.'
