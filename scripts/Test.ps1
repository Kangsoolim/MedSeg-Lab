param([switch]$RealData,[switch]$Browser)
. "$PSScriptRoot\Common.ps1"
$pythonExe = Find-MedSegPython
$pattern = if ($RealData) { 'test_*.py' } else { 'test_adapter.py' }
& $pythonExe -B -m unittest discover -s (Join-Path $ProjectRoot 'tests') -p $pattern -v; Assert-MedSegExit 'Python tests'
& "$PSScriptRoot\Build.ps1"
if ($Browser) {
    Write-Host 'Browser tests require MedSeg-Lab running at http://127.0.0.1:5173/ in another PowerShell.'
    $nodeExe = Find-MedSegNode
    Push-Location (Join-Path $ProjectRoot 'frontend')
    try { & $nodeExe '.\node_modules\@playwright\test\cli.js' test --config '.\playwright.phase1_1.config.ts'; Assert-MedSegExit 'Browser QA' } finally { Pop-Location }
}

