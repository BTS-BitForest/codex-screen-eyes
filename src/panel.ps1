$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (-not $env:SCREEN_EYES_STATE) {
    $data = if ($env:PLUGIN_DATA) { $env:PLUGIN_DATA } else { Join-Path $env:LOCALAPPDATA 'ScreenEyesPlugin' }
    $env:SCREEN_EYES_STATE = Join-Path $data 'state.json'
}
Start-Process -FilePath (Join-Path $root 'bin\ScreenEyes.exe') -ArgumentList 'panel' -WindowStyle Hidden
