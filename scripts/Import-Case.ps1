param([Parameter(Mandatory=$true)][string]$Spec)
. "$PSScriptRoot\Common.ps1"
& (Find-MedSegPython) -B (Join-Path $ProjectRoot 'data_tools\export_package.py') import --spec $Spec --output (Join-Path $ProjectRoot 'frontend\public\demo'); Assert-MedSegExit 'Case import'
& "$PSScriptRoot\Build.ps1"
Write-Host 'Import complete. Reload your local browser; the existing original cases were preserved.'
