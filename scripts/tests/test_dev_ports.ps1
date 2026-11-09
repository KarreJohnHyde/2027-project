# Regression check against real loopback sockets; does not start either app.
$ErrorActionPreference = "Stop"
$launcher = Join-Path (Split-Path -Parent $PSScriptRoot) "dev.ps1"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw "Launcher has syntax errors." }
$function = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq "Test-PortFree"
}, $true)
if (-not $function) { throw "Port probe was not found." }
. ([scriptblock]::Create($function.Extent.Text))

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
try {
    $listener.Start()
    $probePort = $listener.LocalEndpoint.Port
    if (Test-PortFree $probePort) { throw "An active listener was incorrectly considered free." }
    $listener.Stop()
    if (-not (Test-PortFree $probePort)) { throw "A closed listener was incorrectly considered busy." }
    Write-Host "PASS: active and refused loopback connections are classified correctly."
} finally { $listener.Stop() }
