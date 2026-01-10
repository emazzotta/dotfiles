param(
    [switch]$Fast,
    [switch]$f,
    [switch]$Quick,
    [switch]$q
)

$ErrorActionPreference = "Stop"

$isSSH = $env:SSH_CONNECTION -or $env:SSH_CLIENT
if ($isSSH) {
    $scriptPath = $MyInvocation.MyCommand.Path
    $arguments = ""
    if ($Fast -or $f) {
        $arguments = "-Fast"
    }
    elseif ($Quick -or $q) {
        $arguments = "-Quick"
    }

    $action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $arguments"
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName "LeonardoGUI" -Action $action -Principal $principal -Force | Out-Null
    Start-ScheduledTask -TaskName "LeonardoGUI"
    Start-Sleep -Seconds 3
    Unregister-ScheduledTask -TaskName "LeonardoGUI" -Confirm:$false
    exit 0
}

$env:LEONARDO_PROJECTS = "C:\Users\emanuelemazzotta\ProjectsWindows"
$LEONARDO_DIR = "$env:LEONARDO_PROJECTS\leonardo"

if (-not (Test-Path "$LEONARDO_DIR/ops/maven_settings.xml") -and -not (Test-Path "$LEONARDO_DIR/pom.xml")) {
    Write-Error "Not in leonardo project root (missing ops/maven_settings.xml or pom.xml)"
    exit 1
}

Set-Location $LEONARDO_DIR
Write-Host "📁 Running from: $LEONARDO_DIR"

$MvnCommonFlags = "-Prun-leonardo -s ops/maven_settings.xml -pl leonardo-leonardo"

$Mode = "normal"
if ($Fast -or $f) { $Mode = "fast" }
elseif ($Quick -or $q) { $Mode = "quick" }

switch ($Mode) {
    "fast" {
        $Cmd = "mvn exec:exec $MvnCommonFlags"
    }
    "quick" {
        $Cmd = "mvn compile exec:exec $MvnCommonFlags"
    }
    default {
        $Cmd = "mvn clean compile exec:exec $MvnCommonFlags"
    }
}

Write-Host "➤ $Cmd" -ForegroundColor DarkGray
Invoke-Expression $Cmd
