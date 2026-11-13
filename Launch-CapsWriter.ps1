$ErrorActionPreference='Stop'
$root=$PSScriptRoot

# Windows may ignore the initial window style while a console is being created.
# Minimize the app's own console again after startup; its tray monitor hides it.
if(-not ('CapsWriterLauncherWindow' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CapsWriterLauncherWindow {
    [DllImport("kernel32.dll")] public static extern bool FreeConsole();
    [DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint processId);
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr window, uint flags);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr window, int command);
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr window);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr window);
}
'@
}

$appPaths=@()
$names=@('start_client')
if(Test-Path -LiteralPath (Join-Path $root 'start_server.exe')) {
    $names=@('start_server','start_client')
}
foreach($name in $names) {
    $exe=[IO.Path]::GetFullPath((Join-Path $root ($name+'.exe')))
    if(-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Executable not found: $exe"
    }
    $existing=@(Get-Process $name -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq $exe})
    if($existing.Count -eq 0) {
        Start-Process -FilePath $exe -WorkingDirectory $root -WindowStyle Minimized
    }
    $appPaths += $exe
}

for($attempt=0; $attempt -lt 8; $attempt++) {
    foreach($appProcess in @(Get-Process start_server,start_client -ErrorAction SilentlyContinue |
            Where-Object {$appPaths -contains $_.Path})) {
        [CapsWriterLauncherWindow]::FreeConsole() | Out-Null
        if([CapsWriterLauncherWindow]::AttachConsole([uint32]$appProcess.Id)) {
            try {
                $consoleWindow=[CapsWriterLauncherWindow]::GetConsoleWindow()
                $window=[CapsWriterLauncherWindow]::GetAncestor($consoleWindow,2)
                if($window -eq [IntPtr]::Zero) { $window=$consoleWindow }
                if($window -ne [IntPtr]::Zero -and
                        [CapsWriterLauncherWindow]::IsWindowVisible($window) -and
                        -not [CapsWriterLauncherWindow]::IsIconic($window)) {
                    [CapsWriterLauncherWindow]::ShowWindowAsync($window,6) | Out-Null
                }
            } finally {
                [CapsWriterLauncherWindow]::FreeConsole() | Out-Null
            }
        }
    }
    Start-Sleep -Milliseconds 300
}
