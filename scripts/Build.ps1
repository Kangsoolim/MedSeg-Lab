. "$PSScriptRoot\Common.ps1"
$nodeExe = Find-MedSegNode
Push-Location (Join-Path $ProjectRoot 'frontend')
try {
    if (!(Test-Path -LiteralPath '.\node_modules\typescript\bin\tsc')) { throw 'Dependencies missing. Run scripts\Setup.ps1 first.' }
    & $nodeExe '.\node_modules\typescript\bin\tsc' -b; Assert-MedSegExit 'TypeScript'
    & $nodeExe '.\node_modules\vite\bin\vite.js' build; Assert-MedSegExit 'Vite production build'
} finally { Pop-Location }
