param([switch]$CheckOnly, [switch]$Json)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    $package = Get-AppxPackage -Name OpenAI.Codex | Select-Object -First 1
    if ($null -eq $package) { throw 'The installed Codex desktop package was not found.' }
    [xml]$manifest = Get-Content -LiteralPath (Join-Path $package.InstallLocation 'AppxManifest.xml')
    $application = @($manifest.Package.Applications.Application) | Where-Object { $_.Executable -match '(^|[/\\])ChatGPT\.exe$' } | Select-Object -First 1
    if ($null -eq $application) { throw 'The registered Codex application identity was not found.' }
    $appId = $package.PackageFamilyName + '!' + $application.Id
    if ($CheckOnly) {
        $settings = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        $endpoint = [string]$settings.ProxyServer
        if ($endpoint.Contains('=')) {
            $entries = @{}
            foreach ($part in $endpoint.Split(';')) {
                $pair = $part.Split('=', 2)
                if ($pair.Count -eq 2) { $entries[$pair[0].Trim()] = $pair[1].Trim() }
            }
            $endpoint = if ($entries.ContainsKey('https')) { $entries['https'] } else { $entries['http'] }
        }
        $enabled = $settings.ProxyEnable -eq 1 -and -not [string]::IsNullOrWhiteSpace($endpoint)
        $reachable = $false
        if ($enabled) {
            if (-not $endpoint.Contains('://')) { $endpoint = 'http://' + $endpoint }
            $proxyUri = [Uri]$endpoint
            if ($proxyUri.Scheme -notin @('http', 'https') -or $proxyUri.UserInfo) { throw 'Unsupported system proxy format.' }
            $tcp = New-Object Net.Sockets.TcpClient
            try {
                $pending = $tcp.BeginConnect($proxyUri.Host, $proxyUri.Port, $null, $null)
                if ($pending.AsyncWaitHandle.WaitOne(3000)) { $tcp.EndConnect($pending); $reachable = $true }
            } catch { $reachable = $false } finally { $tcp.Dispose() }
        }
        $result = @{status='checked'; Proxy=$endpoint; ProxyEnabled=$enabled; ProxyTcpReachable=$reachable;
            ApplicationId=$appId; GlobalSettingsChanged=$false; ProxyAppliedByLauncher=$false}
    } else {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace ScreenEyes {
    [ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IApplicationActivationManager {
        [PreserveSig] int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string appId,
            [MarshalAs(UnmanagedType.LPWStr)] string arguments, uint options, out uint processId);
    }
    public static class AppActivation {
        [DllImport("ole32.dll", PreserveSig=true)]
        static extern int CoCreateInstance(ref Guid clsid, IntPtr outer, uint context, ref Guid iid,
            [MarshalAs(UnmanagedType.Interface)] out IApplicationActivationManager manager);
        public static uint Open(string appId) {
            Guid clsid = new Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C");
            Guid iid = new Guid("2e941141-7f97-4756-ba1d-9decde894a3d");
            IApplicationActivationManager manager;
            Marshal.ThrowExceptionForHR(CoCreateInstance(ref clsid, IntPtr.Zero, 4, ref iid, out manager));
            try {
                uint processId;
                Marshal.ThrowExceptionForHR(manager.ActivateApplication(appId, "", 0, out processId));
                return processId;
            } finally { Marshal.ReleaseComObject(manager); }
        }
    }
}
'@
        $activatedPid = [ScreenEyes.AppActivation]::Open($appId)
        $packageExe = (Join-Path $package.InstallLocation $application.Executable).Replace('/', '\')
        $windowFound = $false
        for ($attempt=0; $attempt -lt 20; $attempt++) {
            # Electron may hand activation to its existing instance and exit the returned PID.
            $owner = Get-Process ChatGPT -ErrorAction SilentlyContinue | Where-Object {
                $_.Path -eq $packageExe -and $_.MainWindowHandle -ne 0
            } | Select-Object -First 1
            if ($null -ne $owner) { $windowFound = $true; $activatedPid = $owner.Id; break }
            Start-Sleep -Milliseconds 300
        }
        $result = @{status=$(if ($windowFound) {'opened'} else {'activated_no_window'});
            ApplicationId=$appId; ProcessId=$activatedPid; WindowFound=$windowFound; ProxyAppliedByLauncher=$false}
    }
} catch { $result = @{status='error'; message=$_.Exception.Message} }
$dataDirectory = if ($env:SCREEN_EYES_DATA) { $env:SCREEN_EYES_DATA } else { Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'data' }
try {
    New-Item -ItemType Directory -Path $dataDirectory -Force | Out-Null
    @{time=[DateTime]::UtcNow.ToString('o'); checkOnly=[bool]$CheckOnly; result=$result} |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $dataDirectory 'last-launch.json') -Encoding utf8
} catch { }
$result | ConvertTo-Json -Depth 5
if ($result.status -eq 'error') { exit 1 }
