param([string]$Python='python',[switch]$Neural,[switch]$Cuda,[switch]$Dev)
. "$PSScriptRoot\Common.ps1"
if($Cuda){$Neural=$true}
& $Python -B -c "import sys; assert sys.version_info[:2] == (3,11), 'Python 3.11 is the tested supported runtime'"; Assert-MedSegExit 'Check Python 3.11'
$nodeExe=Find-MedSegNode
& $nodeExe -e "const v=process.versions.node.split('.').map(Number); if(!([22,24].includes(v[0]) && (v[0]!==22 || v[1]>=12)))throw Error('Use Node 22.12+ or 24 LTS')"; Assert-MedSegExit 'Check Node'
$backendPython=Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'
if(!(Test-Path -LiteralPath $backendPython)){& $Python -B -m venv (Join-Path $ProjectRoot 'backend\.venv');Assert-MedSegExit 'Create isolated environment'}
& $backendPython -B -c "import sys; assert sys.prefix != sys.base_prefix; assert 'include-system-site-packages = false' in open(sys.prefix+'/pyvenv.cfg').read().lower(), 'Create a fresh isolated venv; inherited course packages are not supported by this installer'";Assert-MedSegExit 'Check environment isolation'
& $backendPython -B -m pip install -r (Join-Path $ProjectRoot 'backend\requirements-core.lock.txt');Assert-MedSegExit 'Install imaging dependencies'
if($Neural){
 $torchIndex=if($Cuda){'https://download.pytorch.org/whl/cu126'}else{'https://download.pytorch.org/whl/cpu'}
 & $backendPython -B -m pip install 'torch==2.8.0' --index-url $torchIndex;Assert-MedSegExit 'Install optional Torch'
 & $backendPython -B -m pip install -r (Join-Path $ProjectRoot 'backend\requirements-neural.lock.txt');Assert-MedSegExit 'Install optional MONAI adapter'
}
if($Dev){& $backendPython -B -m pip install -r (Join-Path $ProjectRoot 'backend\requirements-dev.txt');Assert-MedSegExit 'Install test dependencies'}
$pnpmCommand=Get-Command pnpm -ErrorAction SilentlyContinue
if(!$pnpmCommand){throw 'Install pnpm 11, then rerun. The frozen pnpm-lock.yaml is required.'}
$pnpmVersion=& $pnpmCommand.Source --version
if($pnpmVersion -notmatch '^11\.'){throw 'pnpm 11 is required'}
Push-Location (Join-Path $ProjectRoot 'frontend')
try{& $pnpmCommand.Source install --frozen-lockfile;Assert-MedSegExit 'Install locked frontend'; & $pnpmCommand.Source run build;Assert-MedSegExit 'Build frontend'}finally{Pop-Location}
& $backendPython -B (Join-Path $ProjectRoot 'scripts\Check-Environment.py');Assert-MedSegExit 'Check required imports'
Write-Host 'Ready: .\Start-Phase3B.ps1 . No private data or checkpoint is required.'
