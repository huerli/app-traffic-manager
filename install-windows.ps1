param(
    [string]$ClashDir = '', [string[]]$LogDir = @(),
    [ValidateSet('auto','conda','python')][string]$Runtime = 'auto',
    [string]$CondaPath = '', [string]$PythonPath = '',
    [string]$PythonVersion = '3.12', [string[]]$SearchRoot = @(),
    [string[]]$CondaChannel = @(), [switch]$UseConfiguredChannels
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-runtime.ps1')
$appDir = Join-Path $env:LOCALAPPDATA 'RustDeskClashBypass'
$startup = Join-Path ([Environment]::GetFolderPath('Startup')) 'RustDeskClashBypass.vbs'
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
# Stop only this helper before reinstalling.
Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains((Join-Path $appDir 'bypass.py')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
Copy-Item (Join-Path $PSScriptRoot 'bypass.py') (Join-Path $appDir 'bypass.py') -Force
Copy-Item (Join-Path $PSScriptRoot 'traffic_web.py') (Join-Path $appDir 'traffic_web.py') -Force
Copy-Item (Join-Path $PSScriptRoot 'webdav_sync.py') (Join-Path $appDir 'webdav_sync.py') -Force
Copy-Item (Join-Path $PSScriptRoot 'runtime_paths.py') (Join-Path $appDir 'runtime_paths.py') -Force
Copy-Item (Join-Path $PSScriptRoot 'background_service.py') (Join-Path $appDir 'background_service.py') -Force
Copy-Item (Join-Path $PSScriptRoot 'desktop_app.py') (Join-Path $appDir 'desktop_app.py') -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appDir 'desktop') | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'desktop\flow.png') (Join-Path $appDir 'desktop\flow.png') -Force
Copy-Item (Join-Path $PSScriptRoot 'desktop\flow.ico') (Join-Path $appDir 'desktop\flow.ico') -Force
Copy-Item (Join-Path $PSScriptRoot 'desktop\startup.html') (Join-Path $appDir 'desktop\startup.html') -Force
Copy-Item (Join-Path $PSScriptRoot 'open-manager.py') (Join-Path $appDir 'open-manager.py') -Force
Copy-Item (Join-Path $PSScriptRoot 'windows-bootstrap.py') (Join-Path $appDir 'windows-bootstrap.py') -Force
New-Item -ItemType Directory -Force -Path (Join-Path $appDir 'web') | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'web\index.html') (Join-Path $appDir 'web\index.html') -Force
$selected = New-AppRuntime -AppDir $appDir -Runtime $Runtime -CondaPath $CondaPath -PythonPath $PythonPath -PythonVersion $PythonVersion -SearchRoots $SearchRoot -CondaChannel $CondaChannel -UseConfiguredChannels:$UseConfiguredChannels
$venvPython = $selected.python
$pythonw = $selected.pythonw
& $venvPython -m pip install 'pywebview==6.2.1'
if ($LASTEXITCODE -ne 0) { throw 'Desktop dependency installation failed.' }
if (-not (Test-Path -LiteralPath $pythonw)) { throw "pythonw.exe was not found in the selected runtime: $pythonw" }
$bootstrap = Join-Path $appDir 'windows-bootstrap.py'
[IO.File]::WriteAllText((Join-Path $appDir 'runtime.json'), ($selected | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
$initArgs = @($bootstrap, (Join-Path $appDir 'bypass.py'), 'init', '--data-dir', $appDir)
if ($ClashDir) { $initArgs += @('--clash-dir', $ClashDir) }
foreach ($dir in $LogDir) { $initArgs += @('--log-dir', $dir) }
& $venvPython @initArgs
if ($LASTEXITCODE -ne 0) { throw 'Configuration detection failed.' }
& $venvPython $bootstrap (Join-Path $appDir 'bypass.py') once --data-dir $appDir
if ($LASTEXITCODE -ne 0) { throw "Clash API check failed. Check $appDir\bypass.log and settings.json. Keep Clash Verge running with a loopback external-controller enabled." }
# Preserve the in-app persistence preference when reinstalling.
& $venvPython $bootstrap (Join-Path $appDir 'desktop_app.py') --install-service --data-dir $appDir
if ($LASTEXITCODE -ne 0) { throw 'Background service registration failed.' }
$background = Get-Content (Join-Path $appDir 'background-service.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($background.enabled) { Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $startup + '"') }
Write-Host "Installed. Log: $appDir\bypass.log"

$settings = Get-Content (Join-Path $appDir 'settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$webPort = if ($settings.web_port) { $settings.web_port } else { 17891 }
$url = "http://127.0.0.1:$webPort/"
$programs = [Environment]::GetFolderPath('Programs')
Remove-Item (Join-Path $programs 'Flow Traffic Manager.url') -Force -ErrorAction SilentlyContinue
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $programs 'Flow Traffic Manager.lnk'))
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $bootstrap + '" "' + (Join-Path $appDir 'open-manager.py') + '"'
$shortcut.WorkingDirectory = $appDir
$shortcut.IconLocation = Join-Path $appDir 'desktop\flow.ico'
$shortcut.Description = 'Flow application traffic manager'
$shortcut.Save()
Write-Host "Desktop app installed. Open Flow Traffic Manager from the Start menu. Web fallback: $url"
