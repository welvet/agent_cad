$ErrorActionPreference = 'Stop'
$toolDir = $PSScriptRoot
$venvPython = Join-Path $toolDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & python -m venv (Join-Path $toolDir '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
}
& $venvPython -m pip install -r (Join-Path $toolDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install MCP dependencies' }
Push-Location $toolDir
try {
    & $venvPython -c "import subprocess; from execute import find_freecad_python; subprocess.run([str(find_freecad_python()), '-c', 'import FreeCAD, Part, numpy, PIL; print(FreeCAD.Version())'], check=True)"
    if ($LASTEXITCODE -ne 0) { throw 'FreeCAD runtime verification failed' }
} finally { Pop-Location }
$configuration = @{mcpServers = @{'agent-cad' = @{command = $venvPython; args = @((Join-Path $toolDir 'server.py'))}}}
$configuration | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $toolDir 'mcp-config.local.json') -Encoding utf8
Write-Host 'Ready. Add mcp-config.local.json to your MCP client. Read AGENT_GUIDE.md.'
