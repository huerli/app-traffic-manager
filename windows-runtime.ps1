# Runtime discovery and provisioning. Compatible with Windows PowerShell 5.1.
function Get-CondaCandidates {
    param([string]$CondaPath = '', [string[]]$SearchRoots = @(), [switch]$OnlySearchRoots)
    $found = New-Object 'System.Collections.Generic.List[string]'
    $seen = @{}
    function Add-CondaLocation([string]$Location) {
        if (-not $Location) { return }
        $Location = $Location.Trim().Trim('"')
        $options = @()
        if (Test-Path -LiteralPath $Location -PathType Leaf) {
            if ((Split-Path $Location -Leaf) -match '^(conda\.(exe|bat|cmd)|_conda\.exe)$') { $options += $Location }
        } else {
            foreach ($relative in @('Scripts/conda.exe', 'condabin/conda.exe', 'condabin/conda.bat', 'condabin/conda.cmd', '_conda.exe')) {
                $options += Join-Path $Location $relative
            }
        }
        foreach ($option in $options) {
            if ((Test-Path -LiteralPath $option -PathType Leaf) -and -not $seen.ContainsKey($option)) {
                $seen[$option] = $true
                $found.Add((Get-Item -LiteralPath $option).FullName)
            }
        }
    }
    Add-CondaLocation $CondaPath
    $roots = New-Object 'System.Collections.Generic.List[string]'
    foreach ($root in $SearchRoots) { if ($root) { $roots.Add($root) } }
    if (-not $OnlySearchRoots) {
        Add-CondaLocation $env:CONDA_EXE
        Add-CondaLocation $env:CONDA_PREFIX
        if ($env:CONDA_PYTHON_EXE) { Add-CondaLocation (Split-Path $env:CONDA_PYTHON_EXE -Parent) }
        foreach ($commandName in @('conda.exe', 'conda.bat', 'conda')) {
            Get-Command $commandName -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object { Add-CondaLocation $_.Source }
        }
        foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:ProgramW6432, $env:ProgramData, $env:LOCALAPPDATA, $env:USERPROFILE, $HOME)) {
            if ($root) { $roots.Add($root) }
        }
        if ($env:LOCALAPPDATA) { $roots.Add((Join-Path $env:LOCALAPPDATA 'Programs')) }
        if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
            foreach ($drive in [IO.DriveInfo]::GetDrives()) {
                if ($drive.IsReady -and $drive.DriveType -eq 'Fixed') {
                    foreach ($suffix in @('', 'ProgramFiles', 'Program Files', 'ProgramFiles(x86)', 'Program Files(x86)', 'Program Files (x86)', 'ProgramData', 'Program Data', 'Apps', 'Tools', 'Software', 'Development')) {
                        $roots.Add($(if ($suffix) { Join-Path $drive.RootDirectory.FullName $suffix } else { $drive.RootDirectory.FullName }))
                    }
                }
            }
            foreach ($key in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
                Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'conda|Miniforge|Mambaforge' } | ForEach-Object { if ($_.InstallLocation) { Add-CondaLocation $_.InstallLocation } }
            }
        }
    }
    # Bounded discovery: common roots and named vendor directories; no whole-disk recursion.
    foreach ($root in ($roots | Select-Object -Unique)) {
        Add-CondaLocation $root
        if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
        $children = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'conda|Miniforge|Mambaforge|Continuum' })
        foreach ($child in $children) {
            Add-CondaLocation $child.FullName
            Get-ChildItem -LiteralPath $child.FullName -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'conda|Miniforge|Mambaforge' } | ForEach-Object { Add-CondaLocation $_.FullName }
        }
    }
    return $found.ToArray()
}

function Test-AppPython {
    param([string]$Executable, [string[]]$Prefix = @())
    if (-not $Executable -or $Executable -match '[\\/]WindowsApps[\\/]') { return $null }
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        $code = 'import sys,json; assert sys.version_info >= (3,10); print(json.dumps(dict(executable=sys.executable,version=list(sys.version_info[:3]))))'
        $lines = @(& $Executable @Prefix -c $code 2>$null)
        if ($LASTEXITCODE -ne 0 -or -not $lines.Count) { return $null }
        $result = $lines[-1] | ConvertFrom-Json -ErrorAction Stop
        if (-not $result.executable -or $result.version[0] -ne 3 -or $result.version[1] -lt 10) { return $null }
        return $result
    } catch { return $null }
}

function Get-PythonCandidates {
    param([string]$PythonPath = '')
    if ($PythonPath) { [pscustomobject]@{ Path = $PythonPath; Prefix = @() } }
    foreach ($item in @(@('py', '-3'), @('python.exe', ''), @('python3.exe', ''), @('python', ''))) {
        Get-Command $item[0] -CommandType Application -All -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.Source -notmatch '[\\/]WindowsApps[\\/]') {
                [pscustomobject]@{ Path = $_.Source; Prefix = $(if ($item[1]) { @($item[1]) } else { @() }) }
            }
        }
    }
    if ($env:LOCALAPPDATA) {
        $root = Join-Path $env:LOCALAPPDATA 'Programs/Python'
        Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $path = Join-Path $_.FullName 'python.exe'
            if (Test-Path -LiteralPath $path) { [pscustomobject]@{ Path = $path; Prefix = @() } }
        }
    }
    if ([Environment]::OSVersion.Platform -eq 'Win32NT') {
        foreach ($key in @('HKCU:\Software\Python\PythonCore\*\InstallPath', 'HKLM:\Software\Python\PythonCore\*\InstallPath', 'HKLM:\Software\WOW6432Node\Python\PythonCore\*\InstallPath')) {
            Get-Item $key -ErrorAction SilentlyContinue | ForEach-Object {
                $path = $_.GetValue('ExecutablePath')
                if (-not $path -and $_.GetValue('')) { $path = Join-Path $_.GetValue('') 'python.exe' }
                if ($path -and (Test-Path -LiteralPath $path)) { [pscustomobject]@{ Path = $path; Prefix = @() } }
            }
        }
    }
}

function Install-CondaEnvironment {
    param([string]$Conda, [string]$Prefix, [string]$PythonVersion = '3.12',
          [ValidateSet('create','install')][string]$Operation = 'create',
          [string[]]$CondaChannel = @(), [switch]$UseConfiguredChannels)
    if ($UseConfiguredChannels -and $CondaChannel.Count) { throw 'Use either CondaChannel or UseConfiguredChannels, not both.' }
    $channels = @($CondaChannel)
    if ($UseConfiguredChannels) { $channels = @('configured') }
    elseif (-not $channels.Count) {
        $channels = @('https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge', 'https://conda.anaconda.org/conda-forge')
    }
    foreach ($channel in $channels) {
        if ($channel -eq 'configured') { continue }
        $uri = $null
        if (-not [Uri]::TryCreate($channel, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Query) {
            throw 'CondaChannel must be a complete HTTPS channel URL without credentials or query parameters.'
        }
    }
    $PSNativeCommandUseErrorActionPreference = $false
    $saved = @{}
    foreach ($name in @('CONDA_REMOTE_CONNECT_TIMEOUT_SECS', 'CONDA_REMOTE_READ_TIMEOUT_SECS', 'CONDA_REMOTE_MAX_RETRIES')) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    try {
        [Environment]::SetEnvironmentVariable('CONDA_REMOTE_CONNECT_TIMEOUT_SECS', '8', 'Process')
        [Environment]::SetEnvironmentVariable('CONDA_REMOTE_READ_TIMEOUT_SECS', '60', 'Process')
        [Environment]::SetEnvironmentVariable('CONDA_REMOTE_MAX_RETRIES', '1', 'Process')
        for ($i = 0; $i -lt $channels.Count; $i++) {
            $channel = $channels[$i]
            $attemptPrefix = $Prefix
            $attemptOperation = $Operation
            if ($i -gt 0) {
                # Keep attempts isolated: do not mix channel families or delete a partially created environment.
                $attemptPrefix = $Prefix + '-retry-' + [guid]::NewGuid().ToString('N').Substring(0,8)
                $attemptOperation = 'create'
            }
            $arguments = @($attemptOperation, '--yes', '--prefix', $attemptPrefix)
            if ($channel -ne 'configured') { $arguments += @('--override-channels', '--channel', $channel) }
            $arguments += @("python=$PythonVersion", 'pyyaml>=6.0.2,<7')
            Write-Host "Conda download source: $channel"
            & $Conda @arguments | Out-Host
            if ($LASTEXITCODE -eq 0) { return [pscustomobject]@{ environment=$attemptPrefix; channel=$channel } }
            Write-Warning "Conda setup failed using $channel. Trying the next source, if available."
        }
        throw 'Conda downloads failed for all selected sources. Check the errors above, network access or proxy settings; alternatively pass -CondaChannel with a reachable HTTPS channel. Global Conda configuration was not modified.'
    } finally {
        foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    }
}

function New-AppRuntime {
    param([string]$AppDir, [ValidateSet('auto','conda','python')][string]$Runtime = 'auto',
          [string]$CondaPath = '', [string]$PythonPath = '', [string]$PythonVersion = '3.12', [string[]]$SearchRoots = @(),
          [string[]]$CondaChannel = @(), [switch]$UseConfiguredChannels)
    if ($PythonVersion -notmatch '^3\.(\d+)$' -or [int]$Matches[1] -lt 10) { throw 'PythonVersion must be 3.10 or newer, e.g. 3.12.' }
    $PSNativeCommandUseErrorActionPreference = $false
    $bootstrap = Join-Path $AppDir 'windows-bootstrap.py'
    # Reuse an already working owned runtime before doing discovery or downloads.
    $record = Join-Path $AppDir 'runtime.json'
    if ((Test-Path -LiteralPath $record) -and -not $CondaPath -and -not $PythonPath) {
        $old = Get-Content -LiteralPath $record -Raw -Encoding UTF8 | ConvertFrom-Json
        $probe = Test-AppPython $old.python
        $wanted = $PythonVersion.Split('.')
        $versionOK = $old.kind -ne 'conda' -or ($probe -and $probe.version[0] -eq [int]$wanted[0] -and $probe.version[1] -eq [int]$wanted[1])
        if ($probe -and $versionOK -and ($Runtime -eq 'auto' -or $Runtime -eq $(if ($old.kind -eq 'conda') { 'conda' } else { 'python' }))) {
            & $old.python $bootstrap --check | Out-Host
            if ($LASTEXITCODE -eq 0) { Write-Host "Reusing runtime: $($old.python)"; return $old }
        }
    }
    if ($PythonPath -and $Runtime -eq 'auto') { $Runtime = 'python' }
    if ($Runtime -ne 'python') {
        Write-Host 'Searching for Conda in PATH, Program Files, ProgramData, user folders and common fixed-drive locations...'
        foreach ($candidate in @(Get-CondaCandidates -CondaPath $CondaPath -SearchRoots $SearchRoots)) {
            Write-Host "Checking Conda: $candidate"
            try { & $candidate --version | Out-Host; $working = $LASTEXITCODE -eq 0 } catch { $working = $false }
            if (-not $working) { continue }
            $prefix = Join-Path $AppDir ('conda-env-py' + $PythonVersion.Replace('.', ''))
            $envPython = Join-Path $prefix 'python.exe'
            if (Test-Path -LiteralPath $prefix) {
                # A healthy recorded runtime was reused above. Preserve unrecorded/partial environments.
                $prefix += '-rebuild-' + [guid]::NewGuid().ToString('N').Substring(0,8)
                $envPython = Join-Path $prefix 'python.exe'
            }
            $operation = 'create'
            Write-Host "Preparing independent Conda environment: $prefix (Python $PythonVersion)"
            $download = Install-CondaEnvironment -Conda $candidate -Prefix $prefix -PythonVersion $PythonVersion -Operation $operation -CondaChannel $CondaChannel -UseConfiguredChannels:$UseConfiguredChannels
            $prefix = $download.environment
            $envPython = Join-Path $prefix 'python.exe'
            $ready = Test-AppPython $envPython
            if (-not $ready -or (($ready.version[0..1] -join '.') -ne $PythonVersion)) { throw 'Conda completed, but the requested environment Python version could not be verified.' }
            & $envPython $bootstrap --check | Out-Host
            if ($LASTEXITCODE -ne 0) { throw 'The Conda runtime dependency check failed.' }
            return [pscustomobject]@{ kind='conda'; python=$envPython; pythonw=(Join-Path $prefix 'pythonw.exe'); environment=$prefix; conda=$candidate; version=$PythonVersion; channel=$download.channel }
        }
        if ($Runtime -eq 'conda') { throw 'No working Conda installation found. Pass -CondaPath to the installation folder or conda.exe.' }
    }
    foreach ($candidate in @(Get-PythonCandidates -PythonPath $PythonPath)) {
        Write-Host "Checking Python: $($candidate.Path)"
        $probe = Test-AppPython -Executable $candidate.Path -Prefix $candidate.Prefix
        if (-not $probe) { continue }
        Write-Host "Preparing venv from: $($probe.executable)"
        $prefix = Join-Path $AppDir 'venv'
        & $probe.executable -m venv $prefix | Out-Host
        if ($LASTEXITCODE -ne 0) { continue }
        $envPython = Join-Path $prefix 'Scripts/python.exe'
        & $envPython -m pip install 'PyYAML>=6.0.2,<7' | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Installing PyYAML in the venv failed.' }
        & $envPython $bootstrap --check | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'The venv runtime dependency check failed.' }
        return [pscustomobject]@{ kind='venv'; python=$envPython; pythonw=(Join-Path $prefix 'Scripts/pythonw.exe'); environment=$prefix; conda=$null; version=($probe.version[0..1] -join '.') }
    }
    throw 'No working Python 3.10+ or Conda found. Use -CondaPath, -SearchRoot, or -PythonPath to supply a custom location.'
}
