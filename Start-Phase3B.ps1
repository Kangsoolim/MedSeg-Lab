param([switch]$NoBrowser,[switch]$CheckOnly,[int]$StopAfterSeconds=0)
. "$PSScriptRoot\scripts\Common.ps1"
$backendPython=Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'
if(!(Test-Path -LiteralPath $backendPython)){throw 'Run scripts/Setup-Phase3B.ps1 first.'}
& $backendPython -B (Join-Path $ProjectRoot 'scripts\Check-Environment.py');Assert-MedSegExit 'Check dependencies'
$nodeExe=Find-MedSegNode
if(!(Test-Path -LiteralPath (Join-Path $ProjectRoot 'frontend\dist\index.html'))){throw 'Frontend build missing; run Setup-Phase3B.ps1.'}
# Refuse any pre-existing listener, even another MedSeg instance: no ownership ambiguity.
foreach($port in @(8008,5173)){
 $listener=Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
 if($listener){throw "Port $port is already in use. Stop its owning service or use its existing page."}
}
if($CheckOnly){Write-Host 'Dependencies, build and ports ready.';return}
$backendProcess=$null;$frontendProcess=$null;$stopFile=''
try{
 New-Item -ItemType Directory -Path (Join-Path $ProjectRoot 'runs') -Force | Out-Null
 $stamp=Get-Date -Format 'yyyyMMdd_HHmmss_fff'
 $stopFile='.stop-'+[Guid]::NewGuid().ToString('N')
 $runtime=& $backendPython -B (Join-Path $ProjectRoot 'backend\runtime.py') | ConvertFrom-Json;Assert-MedSegExit 'Resolve runtime'
 $prior=[Environment]::GetEnvironmentVariable('PYTHONPATH','Process')
 try{
  $env:PYTHONPATH=$runtime.pythonpath
  $backendProcess=Start-Process -FilePath $runtime.executable -ArgumentList @('-S','-B','-m','backend.launch_server',$stopFile) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $ProjectRoot "runs\phase3b-$stamp.stdout.log") -RedirectStandardError (Join-Path $ProjectRoot "runs\phase3b-$stamp.stderr.log")
 }finally{if($null -eq $prior){Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue}else{$env:PYTHONPATH=$prior}}
 $ready=$false
 for($attempt=0;$attempt -lt 80;$attempt++){
  if($backendProcess.HasExited){throw 'Backend exited; inspect runs/phase3b-*.stderr.log'}
  try{$h=Invoke-RestMethod 'http://127.0.0.1:8008/api/v1/health' -TimeoutSec 1;if($h.version -eq 'phase2a-v1' -and $h.service_pid -eq $backendProcess.Id){$ready=$true;break}}catch{}
  Start-Sleep -Milliseconds 250
 }
 if(!$ready){throw 'Backend startup timeout'}
 $frontendReady=$false
 $frontendProcess=Start-Process -FilePath $nodeExe -ArgumentList @((Join-Path $ProjectRoot 'frontend\node_modules\vite\bin\vite.js'),'preview','--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory (Join-Path $ProjectRoot 'frontend') -WindowStyle Hidden -PassThru
 for($attempt=0;$attempt -lt 40;$attempt++){
  if($frontendProcess.HasExited){throw 'Frontend exited'}
  try{$null=Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 1;$frontendReady=$true;break}catch{Start-Sleep -Milliseconds 250}
 }
 if(!$frontendReady){throw 'Frontend startup timeout'}
 if(!$NoBrowser){Start-Process 'http://127.0.0.1:5173/'}
 Write-Host 'MedSeg-Lab: http://127.0.0.1:5173/ . Ctrl+C closes only services started here.'
 $deadline=if($StopAfterSeconds -gt 0){(Get-Date).AddSeconds($StopAfterSeconds)}else{$null}
 while(!$backendProcess.HasExited -and !$frontendProcess.HasExited){if($deadline -and (Get-Date) -ge $deadline){break};Start-Sleep -Milliseconds 250}
}finally{
 # Exact Process objects are owned by this launcher; WorkerOwner kills owned workers on backend exit.
 if($frontendProcess -and !$frontendProcess.HasExited){$frontendProcess.Kill();$frontendProcess.WaitForExit()}
 if($backendProcess -and !$backendProcess.HasExited){
  [IO.File]::WriteAllText((Join-Path $ProjectRoot ('runs\'+$stopFile)),'stop')
  if(!$backendProcess.WaitForExit(15000)){$backendProcess.Kill();$backendProcess.WaitForExit()}
 }
}
