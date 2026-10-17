$ErrorActionPreference = 'Stop'
$appDir = Join-Path $env:LOCALAPPDATA 'RustDeskClashBypass'
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'RustDeskClashBypass.vbs'
Remove-Item $startup -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains((Join-Path $appDir 'bypass.py')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
if (Test-Path (Join-Path $appDir 'settings.json')) {
  $runtimeFile = Join-Path $appDir 'runtime.json'
  $python = Join-Path $appDir 'venv\Scripts\python.exe'
  $arguments = @((Join-Path $appDir 'bypass.py'), 'uninstall', '--data-dir', $appDir)
  if (Test-Path -LiteralPath $runtimeFile) {
    $runtime = Get-Content -LiteralPath $runtimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $python = $runtime.python
    $arguments = @((Join-Path $appDir 'windows-bootstrap.py')) + $arguments
  }
  & $python @arguments
  if ($LASTEXITCODE -ne 0) { throw 'Could not remove Clash changes. Start Clash Verge and rerun uninstall.' }
}
Write-Host "Uninstalled. Settings and backup retained in $appDir"

Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Flow Traffic Manager.url') -Force -ErrorAction SilentlyContinue

Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Flow Traffic Manager.lnk') -Force -ErrorAction SilentlyContinue
