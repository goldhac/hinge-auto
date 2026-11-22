# What the "Hinge Bot" desktop shortcut runs: boot the emulator if needed,
# open Hinge, ask how many likes, run the bot.

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$Sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "$env:LOCALAPPDATA\Android\Sdk" }
$adb = "$Sdk\platform-tools\adb.exe"
$Avd = 'Hinge_Pixel10'

function Fail($msg) { Write-Host "`n$msg" -ForegroundColor Red; Read-Host 'Press Enter to close'; exit 1 }

if (-not (Test-Path $adb)) { Fail 'Android SDK not found. Run the installer first.' }

$running = (& $adb devices) -match '^emulator-\d+\s+device'
if (-not $running) {
    Write-Host 'Starting the emulator...'
    # Start-Process detaches it, so closing this window doesn't kill the phone.
    Start-Process "$Sdk\emulator\emulator.exe" -ArgumentList '-avd', $Avd
    & $adb wait-for-device
}
Write-Host 'Waiting for Android to finish booting...'
for ($i = 0; $i -lt 100; $i++) {
    if ((& $adb shell getprop sys.boot_completed 2>$null) -match '1') { break }
    Start-Sleep 3
}

if (-not (& $adb shell pm path co.hinge.app 2>$null)) {
    Fail 'Hinge is not installed in the emulator. Install it from the Play Store, log in, then run this again.'
}
& $adb shell monkey -p co.hinge.app -c android.intent.category.LAUNCHER 1 | Out-Null
Start-Sleep 8

Write-Host ''
Write-Host 'Free Hinge allows about 8 likes a day. Hinge+ has no cap.'
$n = Read-Host 'How many likes this run? [8]'
if (-not $n) { $n = '8' }
if ($n -notmatch '^\d+$' -or [int]$n -lt 1) { Fail "Not a number: $n" }

Write-Host "`nRunning. Leave the emulator on the Discover tab. Ctrl+C stops it.`n" -ForegroundColor Green
& "$PSScriptRoot\.venv\Scripts\python.exe" -u main.py --likes $n
Read-Host "`nFinished. Press Enter to close"
