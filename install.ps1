# HingeAuto one-shot installer for Windows 10/11.
#
#   irm https://raw.githubusercontent.com/goldhac/hinge-auto/main/install.ps1 | iex
#
# Installs Python, Java and the Android SDK (no Android Studio), builds the
# Hinge_Pixel10 emulator, downloads the code to %USERPROFILE%\hinge-auto,
# asks for a Gemini key, and puts a "Hinge Bot" shortcut on the desktop.
# Safe to re-run: every step skips itself when already done, and re-running
# updates the code without touching .env.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is 10x slower with the progress bar

$Dir   = if ($env:HINGE_DIR) { $env:HINGE_DIR } else { "$HOME\hinge-auto" }
$Sdk   = "$env:LOCALAPPDATA\Android\Sdk"
$Avd   = 'Hinge_Pixel10'
$Image = 'system-images;android-34;google_apis_playstore;x86_64'
$ToolsZip = 'https://dl.google.com/android/repository/commandlinetools-win-13114758_latest.zip'
$RepoZip  = 'https://github.com/goldhac/hinge-auto/archive/refs/heads/main.zip'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Winget-Install($id) {
    winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {   # -1978335189 = already installed
        throw "winget could not install $id (exit $LASTEXITCODE)"
    }
    Refresh-Path
}

Write-Host @"

  HingeAuto installer
  -------------------
  Automating Hinge breaks its Terms of Service and the account can be
  banned with no appeal. The bot sends real likes and messages.

"@ -ForegroundColor Yellow

if (-not (Have winget)) { throw 'winget is missing. Install "App Installer" from the Microsoft Store, then re-run.' }

# ---- 1. Python + Java ----------------------------------------------------
Step 'Python 3.13'
$py = $null
if (Have py) { try { & py -3.13 -c 'import sys' 2>$null; if ($LASTEXITCODE -eq 0) { $py = @('py', '-3.13') } } catch {} }
if (-not $py) {
    Winget-Install 'Python.Python.3.13'
    $py = @('py', '-3.13')
}

Step 'Java 17 (needed by the Android SDK tools)'
if (-not (Have java)) { Winget-Install 'Microsoft.OpenJDK.17' }
if (-not $env:JAVA_HOME) {
    $java = Get-Command java -ErrorAction SilentlyContinue
    $env:JAVA_HOME = if ($java) { Split-Path (Split-Path $java.Source) }
                     else { (Get-ChildItem "$env:ProgramFiles\Microsoft\jdk-17*" -Directory | Select-Object -First 1).FullName }
    if (-not $env:JAVA_HOME) { throw 'Java installed but not found. Open a new PowerShell window and re-run.' }
}

# ---- 2. Android SDK ------------------------------------------------------
$SdkMgr = "$Sdk\cmdline-tools\latest\bin\sdkmanager.bat"
$AvdMgr = "$Sdk\cmdline-tools\latest\bin\avdmanager.bat"
Step 'Android command-line tools'
if (-not (Test-Path $SdkMgr)) {
    $tmp = Join-Path $env:TEMP 'hinge-cmdline-tools'
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-WebRequest $ToolsZip -OutFile "$tmp.zip"
    Expand-Archive "$tmp.zip" $tmp -Force
    New-Item -ItemType Directory -Force "$Sdk\cmdline-tools" | Out-Null
    Move-Item "$tmp\cmdline-tools" "$Sdk\cmdline-tools\latest"
    Remove-Item "$tmp.zip"
}
$env:ANDROID_HOME = $Sdk
[Environment]::SetEnvironmentVariable('ANDROID_HOME', $Sdk, 'User')

Step 'Emulator + Android 14 Play Store image (about 2 GB, one time)'
('y' + "`n") * 30 | & $SdkMgr --licenses | Out-Null
& $SdkMgr 'platform-tools' 'emulator' $Image
if ($LASTEXITCODE -ne 0) { throw 'sdkmanager failed' }

# adb on PATH for later terminals
$pt = "$Sdk\platform-tools"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath -notlike "*$pt*") { [Environment]::SetEnvironmentVariable('Path', "$userPath;$pt", 'User') }
Refresh-Path

# ---- 3. Virtualization ---------------------------------------------------
Step 'Checking hardware acceleration'
$accel = & "$Sdk\emulator\emulator.exe" -accel-check 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Write-Host $accel
    Write-Host 'Turning on Windows Hypervisor Platform (Windows will ask for admin).' -ForegroundColor Yellow
    Start-Process dism -Verb RunAs -Wait -ArgumentList '/online /enable-feature /featurename:HypervisorPlatform /all /norestart'
    Write-Host "`nRESTART THE PC, then run the same install command again." -ForegroundColor Yellow
    Write-Host 'If it still fails after a restart, turn on virtualization (VT-x / SVM) in the BIOS.'
    return
}

# ---- 4. Emulator (Pixel 10 screen: 1080x2424 @ 420dpi) -------------------
Step "Emulator '$Avd'"
$avdDir = "$HOME\.android\avd\$Avd.avd"
if (-not (Test-Path $avdDir)) {
    'no' | & $AvdMgr create avd -n $Avd -k $Image -d pixel_7 --force
    if ($LASTEXITCODE -ne 0) { throw 'avdmanager failed' }
    # The bot's tap coordinates are calibrated for this exact screen.
    $want = @{
        'hw.lcd.width' = '1080'; 'hw.lcd.height' = '2424'; 'hw.lcd.density' = '420'
        'hw.ramSize' = '4096'; 'disk.dataPartition.size' = '8G'; 'hw.keyboard' = 'yes'
        'skin.name' = '1080x2424'; 'skin.path' = '_no_skin'; 'PlayStore.enabled' = 'true'
    }
    $ini = "$avdDir\config.ini"
    $lines = Get-Content $ini | Where-Object { $want.Keys -notcontains ($_ -split '=', 2)[0].Trim() }
    $lines += $want.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
    Set-Content $ini $lines -Encoding ASCII
}

# ---- 5. Code -------------------------------------------------------------
Step "Code -> $Dir"
$tmp = Join-Path $env:TEMP 'hinge-auto-src'
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Invoke-WebRequest $RepoZip -OutFile "$tmp.zip"
Expand-Archive "$tmp.zip" $tmp -Force
New-Item -ItemType Directory -Force $Dir | Out-Null
# .env and personal files are not in the zip, so they survive updates.
robocopy "$tmp\hinge-auto-main" $Dir /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "copying code failed (robocopy $LASTEXITCODE)" }
Remove-Item $tmp, "$tmp.zip" -Recurse -Force

Step 'Python packages'
if (-not (Test-Path "$Dir\.venv\Scripts\python.exe")) {
    & $py[0] $py[1] -m venv "$Dir\.venv"
}
& "$Dir\.venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "$Dir\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

# ---- 6. Gemini key -------------------------------------------------------
Step 'Gemini API key'
$envFile = "$Dir\.env"
$haveKey = (Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^GEMINI_API_KEY=\S' -Quiet)
while (-not $haveKey) {
    Write-Host 'Opening Google AI Studio. Click "Create API key", copy it, paste it here.'
    Start-Process 'https://aistudio.google.com/apikey'
    $key = (Read-Host 'Gemini API key').Trim()
    try {
        Invoke-WebRequest "https://generativelanguage.googleapis.com/v1beta/models?key=$key" -UseBasicParsing | Out-Null
        $rest = if (Test-Path $envFile) { Get-Content $envFile | Where-Object { $_ -notmatch '^GEMINI_API_KEY=' } } else { @() }
        Set-Content $envFile (@("GEMINI_API_KEY=$key") + $rest) -Encoding ASCII
        $haveKey = $true
        Write-Host 'Key works.' -ForegroundColor Green
    } catch {
        Write-Host 'Google rejected that key. Try again.' -ForegroundColor Red
    }
}

# ---- 7. Desktop shortcut -------------------------------------------------
Step 'Desktop shortcut'
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Hinge Bot.lnk")
$lnk.TargetPath = 'powershell.exe'
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Dir\start.ps1`""
$lnk.WorkingDirectory = $Dir
$lnk.Save()

# ---- 8. First boot -------------------------------------------------------
Step 'Booting the emulator for the one-time Hinge login'
Start-Process "$Sdk\emulator\emulator.exe" -ArgumentList '-avd', $Avd
Write-Host @"

  Installed. One last manual step, in the emulator window that just opened
  (first boot takes 2-5 minutes):

    1. Open Play Store, sign in with a Google account.
    2. Install Hinge, log in, and open the Discover tab.

  After that, just double-click "Hinge Bot" on your desktop.

"@ -ForegroundColor Green
