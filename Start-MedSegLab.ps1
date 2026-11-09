param([switch]$Dev, [switch]$NoBrowser, [switch]$Rebuild, [ValidateRange(1024,65535)][int]$Port = 5173)
. "$PSScriptRoot\scripts\Common.ps1"
if ($Rebuild) { & "$PSScriptRoot\scripts\Build.ps1" }
$address = "http://127.0.0.1:$Port/"
if ($Dev) {
    $nodeExe = Find-MedSegNode
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try { & $nodeExe '.\node_modules\vite\bin\vite.js' --host 127.0.0.1 --port $Port --strictPort; Assert-MedSegExit 'Vite' } finally { Pop-Location }
} else {
    $site = Join-Path $ProjectRoot 'frontend\dist'
    if (!(Test-Path -LiteralPath (Join-Path $site 'index.html'))) { & "$PSScriptRoot\scripts\Build.ps1" }
    if (!$NoBrowser) { Start-Process $address }
    Write-Host "MedSeg-Lab: $address  (local only; Ctrl+C to stop)"
    & (Find-MedSegPython) -B -m http.server $Port --bind 127.0.0.1 --directory $site
    Assert-MedSegExit 'Local HTTP server'
}
