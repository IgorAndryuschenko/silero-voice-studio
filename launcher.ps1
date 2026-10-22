param([switch]$CheckOnly, [switch]$InstallVCRuntime)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$setupDir = Join-Path $PSScriptRoot '.setup'
New-Item -ItemType Directory -Path $setupDir -Force | Out-Null
$logName = if ($InstallVCRuntime) { 'vc-runtime.log' } else { 'launcher.log' }
Start-Transcript -Path (Join-Path $setupDir $logName) -Append | Out-Null

function Get-VerifiedInstaller([string]$Url, [string]$Name, [string]$Publisher) {
    $installer = Join-Path $setupDir $Name
    Write-Host "Downloading $Name from the official publisher..."
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $installer
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $Publisher) {
        throw "Installer signature validation failed: $Name"
    }
    return $installer
}

function Test-Python([string]$Executable) {
    if (-not $Executable -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        & $Executable -c 'import sys,struct,venv,tkinter; assert (3,10) <= sys.version_info[:2] <= (3,13); assert struct.calcsize(chr(80))==8' 2>$null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

try {
    if ($InstallVCRuntime) {
        $vcInstaller = Get-VerifiedInstaller 'https://aka.ms/vs/17/release/vc_redist.x64.exe' 'vc_redist.x64.exe' 'Microsoft Corporation'
        $vcProcess = Start-Process -FilePath $vcInstaller -ArgumentList '/install', '/quiet', '/norestart' -Wait -PassThru -WindowStyle Hidden
        if ($vcProcess.ExitCode -notin @(0, 1638, 3010)) { throw "Visual C++ setup failed: $($vcProcess.ExitCode)" }
        if ($vcProcess.ExitCode -eq 3010) { Write-Host 'Visual C++ requests a Windows restart if DLL errors persist.' }
    } else {
        if ([Environment]::Is64BitOperatingSystem -eq $false) { throw '64-bit Windows 10 or later is required.' }
        $pythonCandidates = @(
            (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
            (Join-Path $setupDir 'python\python.exe')
        )
        $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($pyLauncher) {
            foreach ($version in @('3.13', '3.12', '3.11', '3.10')) {
                try {
                    $foundPython = & $pyLauncher.Source "-$version" -c 'import sys; print(sys.executable)' 2>$null
                    if ($LASTEXITCODE -eq 0 -and $foundPython) { $pythonCandidates += [string]$foundPython }
                } catch { }
            }
        }
        foreach ($version in @('313', '312', '311', '310')) {
            $pythonCandidates += Join-Path $env:LOCALAPPDATA "Programs\Python\Python$version\python.exe"
            $pythonCandidates += Join-Path $env:ProgramFiles "Python$version\python.exe"
        }
        $pathPython = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pathPython -and $pathPython.Source -notmatch 'WindowsApps') { $pythonCandidates += $pathPython.Source }
        $pythonExe = $null
        foreach ($candidate in $pythonCandidates) {
            if (Test-Python $candidate) { $pythonExe = $candidate; break }
        }
        if (-not $pythonExe) {
            $pythonInstaller = Get-VerifiedInstaller 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.exe' 'python-3.13.17-amd64.exe' 'Python Software Foundation'
            $pythonTarget = Join-Path $setupDir 'python'
            $installArguments = '/quiet InstallAllUsers=0 Include_launcher=0 Include_test=0 Include_tcltk=1 Include_pip=1 AssociateFiles=0 Shortcuts=0 PrependPath=0 TargetDir="' + $pythonTarget + '"'
            $pythonProcess = Start-Process -FilePath $pythonInstaller -ArgumentList $installArguments -Wait -PassThru -WindowStyle Hidden
            if ($pythonProcess.ExitCode -notin @(0, 3010)) { throw "Python installation failed: $($pythonProcess.ExitCode)" }
            $pythonExe = Join-Path $pythonTarget 'python.exe'
            if (-not (Test-Python $pythonExe)) { throw 'Installed Python did not pass the Python/Tkinter check.' }
        }
        $venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $venvPython)) {
            Write-Host 'Creating a separate Python environment...'
            & $pythonExe -m venv (Join-Path $PSScriptRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check write access and free disk space.' }
        }
        if (-not (Test-Python $venvPython)) { throw 'The .venv environment is damaged or unsupported. Rename .venv and run again.' }
        $bootstrapArguments = @((Join-Path $PSScriptRoot 'bootstrap.py'))
        if ($CheckOnly) { $bootstrapArguments += '--check' }
        $savedErrorPreference = $ErrorActionPreference
        try {
            # Windows PowerShell treats native stderr (including harmless Python warnings)
            # as error records. Capture it for the log, then trust the process exit code.
            $ErrorActionPreference = 'Continue'
            & $venvPython @bootstrapArguments 2>&1 | ForEach-Object { Write-Host $_ }
            $bootstrapExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $savedErrorPreference }
        if ($bootstrapExitCode -ne 0) { throw "Application setup/check failed (exit $bootstrapExitCode)." }
    }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 1
}
Stop-Transcript | Out-Null
exit 0
