$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path $PSScriptRoot -Parent
function Find-MedSegPython {
    $candidates = @((Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'), (Join-Path $ProjectRoot '.venv\Scripts\python.exe'))
    foreach ($candidate in $candidates) { if (Test-Path -LiteralPath $candidate) { return $candidate } }
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { return $pythonCommand.Source }
    throw 'Python 3.10+ not found. Install Python or create .venv. See README.'
}
function Find-MedSegNode {
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCommand) { return $nodeCommand.Source }
    $candidate = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (Test-Path -LiteralPath $candidate) { return $candidate }
    throw 'Node.js 20.19+ or 22.12+ is required for building. The prebuilt app needs only Python.'
}
function Assert-MedSegExit([string]$Step) { if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)." } }
