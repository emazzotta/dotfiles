param(
    [switch]$Fast,
    [switch]$f,
    [switch]$Quick,
    [switch]$q
)

$logFile = "$env:TEMP\leorun.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Log {
    param([string]$Message)
    "$timestamp - $Message" | Out-File -FilePath $logFile -Append -Encoding UTF8
    Write-Host $Message
}

Write-Log "➡️ Starting leorun.ps1..."

$ErrorActionPreference = "Stop"

Write-Log "🔍 Checking if running via SSH..."
$isSSH = $env:SSH_CONNECTION -or $env:SSH_CLIENT
Write-Host "   SSH_CONNECTION: $env:SSH_CONNECTION" -ForegroundColor DarkGray
Write-Host "   SSH_CLIENT: $env:SSH_CLIENT" -ForegroundColor DarkGray
"$timestamp -    SSH_CONNECTION: $env:SSH_CONNECTION" | Out-File -FilePath $logFile -Append
"$timestamp -    SSH_CLIENT: $env:SSH_CLIENT" | Out-File -FilePath $logFile -Append

if ($isSSH) {
    Write-Log "✓ SSH session detected - will create scheduled task to run in interactive session"

    $scriptPath = $MyInvocation.MyCommand.Path
    Write-Host "   Original script path: $scriptPath" -ForegroundColor DarkGray
    "$timestamp -    Original script path: $scriptPath" | Out-File -FilePath $logFile -Append

    $isNetworkPath = $scriptPath -match "^\\\\[^\\]+"
    if ($isNetworkPath) {
        Write-Host "   ⚠️  Network path detected - copying to local temp directory" -ForegroundColor Yellow
        $localScriptPath = "$env:TEMP\leorun_temp.ps1"
        try {
            Copy-Item -Path $scriptPath -Destination $localScriptPath -Force
            Write-Host "   ✓ Copied to: $localScriptPath" -ForegroundColor Green
            $scriptPath = $localScriptPath
        }
        catch {
            Write-Host "   ❌ Failed to copy script locally: $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "   Attempting to use network path anyway..." -ForegroundColor Yellow
        }
    }

    $arguments = ""
    if ($Fast -or $f) {
        $arguments = "-Fast"
        Write-Host "   Mode: Fast" -ForegroundColor DarkGray
    }
    elseif ($Quick -or $q) {
        $arguments = "-Quick"
        Write-Host "   Mode: Quick" -ForegroundColor DarkGray
    }
    else {
        Write-Host "   Mode: Normal (full build)" -ForegroundColor DarkGray
    }

    $pwshCommand = "pwsh.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $arguments"
    Write-Host "   Command: $pwshCommand" -ForegroundColor DarkGray

    try {
        Write-Host "📋 Creating scheduled task 'LeonardoGUI'..." -ForegroundColor Cyan

        $action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-ExecutionPolicy Bypass -File `"$scriptPath`" $arguments"
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -Hidden:$false `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2)

        Write-Host "   Settings: Window visible, 2hr timeout" -ForegroundColor DarkGray

        $task = Register-ScheduledTask -TaskName "LeonardoGUI" -Action $action -Principal $principal -Settings $settings -Force
        Write-Host "✓ Scheduled task created successfully" -ForegroundColor Green

        Write-Host "▶️  Starting scheduled task..." -ForegroundColor Cyan
        Start-ScheduledTask -TaskName "LeonardoGUI"
        Write-Host "✓ Scheduled task started" -ForegroundColor Green

        Write-Host "⏳ Waiting 5 seconds for task to execute..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 5

        Write-Host "🔍 Checking task execution status..." -ForegroundColor Cyan
        try {
            $taskInfo = Get-ScheduledTaskInfo -TaskName "LeonardoGUI" 2>$null
            if ($taskInfo) {
                Write-Host "   Last run time: $($taskInfo.LastRunTime)" -ForegroundColor DarkGray
                Write-Host "   Last result: $($taskInfo.LastTaskResult) $(if ($taskInfo.LastTaskResult -eq 0) { '(Success)' } else { '(Error)' })" -ForegroundColor $(if ($taskInfo.LastTaskResult -eq 0) { 'Green' } else { 'Red' })

                if ($taskInfo.LastTaskResult -ne 0) {
                    Write-Host "" -ForegroundColor Yellow
                    Write-Host "⚠️  Task returned error code: 0x$($taskInfo.LastTaskResult.ToString('X'))" -ForegroundColor Yellow
                    Write-Host "   Common causes:" -ForegroundColor DarkGray
                    Write-Host "   - Network path access denied (if UNC path)" -ForegroundColor DarkGray
                    Write-Host "   - Script execution policy blocked" -ForegroundColor DarkGray
                    Write-Host "   - Maven/Java not found in PATH" -ForegroundColor DarkGray
                    Write-Host "" -ForegroundColor Yellow
                    Write-Host "   View detailed logs with:" -ForegroundColor Yellow
                    Write-Host "   Get-WinEvent -LogName Microsoft-Windows-TaskScheduler/Operational -MaxEvents 5" -ForegroundColor Cyan
                }
            }
        }
        catch {
            Write-Host "   (Task info unavailable - task may have already completed)" -ForegroundColor DarkGray
        }

        Write-Host "🗑️  Cleaning up scheduled task..." -ForegroundColor DarkGray
        Unregister-ScheduledTask -TaskName "LeonardoGUI" -Confirm:$false
        Write-Host "✓ Scheduled task removed" -ForegroundColor Green

        if ($isNetworkPath -and (Test-Path $localScriptPath)) {
            Remove-Item $localScriptPath -Force -ErrorAction SilentlyContinue
            Write-Host "✓ Temporary script file cleaned up" -ForegroundColor Green
        }

        Write-Host "" -ForegroundColor Green
        Write-Host "✓ Leonardo should now be starting in an interactive session on your desktop" -ForegroundColor Green
        Write-Host "  Check Task Manager or look for the Leonardo GUI window" -ForegroundColor Yellow
        Write-Host "" -ForegroundColor Cyan
        Write-Host "📝 Diagnostic log available at:" -ForegroundColor Cyan
        Write-Host "   $logFile" -ForegroundColor Yellow
        Write-Host "   View with: cat $logFile" -ForegroundColor DarkGray
        exit 0
    }
    catch {
        Write-Host "" -ForegroundColor Red
        Write-Host "❌ Error during scheduled task execution:" -ForegroundColor Red
        Write-Host "   $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "" -ForegroundColor Yellow
        Write-Host "Troubleshooting tips:" -ForegroundColor Yellow
        Write-Host "  1. Check if Task Scheduler service is running: Get-Service Schedule" -ForegroundColor DarkGray
        Write-Host "  2. Verify you have permissions to create scheduled tasks" -ForegroundColor DarkGray
        Write-Host "  3. Check Task Scheduler event logs for details" -ForegroundColor DarkGray
        exit 1
    }
}
else {
    Write-Log "✓ Running directly (not via SSH) - proceeding with normal execution"
}

Write-Host ""
Write-Log "🔧 Initializing Leonardo environment..."

$env:LEONARDO_PROJECTS = "C:\Users\emanuelemazzotta\ProjectsWindows"
$LEONARDO_DIR = "$env:LEONARDO_PROJECTS\leonardo"

Write-Host "   LEONARDO_DIR: $LEONARDO_DIR" -ForegroundColor DarkGray

Write-Host "🔍 Validating Leonardo project structure..." -ForegroundColor Cyan
$hasMavenSettings = Test-Path "$LEONARDO_DIR/ops/maven_settings.xml"
$hasPom = Test-Path "$LEONARDO_DIR/pom.xml"

Write-Host "   ops/maven_settings.xml: $(if ($hasMavenSettings) { '✓ Found' } else { '✗ Missing' })" -ForegroundColor $(if ($hasMavenSettings) { 'Green' } else { 'Red' })
Write-Host "   pom.xml: $(if ($hasPom) { '✓ Found' } else { '✗ Missing' })" -ForegroundColor $(if ($hasPom) { 'Green' } else { 'Red' })

if (-not $hasMavenSettings -and -not $hasPom) {
    Write-Host ""
    Write-Host "❌ Not in leonardo project root (missing ops/maven_settings.xml or pom.xml)" -ForegroundColor Red
    Write-Host "   Expected location: $LEONARDO_DIR" -ForegroundColor Yellow
    exit 1
}

Write-Host "✓ Project structure validated" -ForegroundColor Green

Set-Location $LEONARDO_DIR
Write-Host "📁 Working directory: $LEONARDO_DIR" -ForegroundColor Cyan

$MvnCommonFlags = "-Prun-leonardo -s ops/maven_settings.xml -pl leonardo-leonardo"

$Mode = "normal"
if ($Fast -or $f) { $Mode = "fast" }
elseif ($Quick -or $q) { $Mode = "quick" }

Write-Host ""
Write-Host "🚀 Preparing Maven execution..." -ForegroundColor Cyan
Write-Host "   Mode: $Mode" -ForegroundColor Yellow

switch ($Mode) {
    "fast" {
        Write-Host "   Skip: clean, compile (exec only)" -ForegroundColor DarkGray
        $Cmd = "mvn exec:exec $MvnCommonFlags"
    }
    "quick" {
        Write-Host "   Skip: clean (compile + exec)" -ForegroundColor DarkGray
        $Cmd = "mvn compile exec:exec $MvnCommonFlags"
    }
    default {
        Write-Host "   Full build: clean + compile + exec" -ForegroundColor DarkGray
        $Cmd = "mvn clean compile exec:exec $MvnCommonFlags"
    }
}

Write-Host ""
Write-Log "▶️  Executing: $Cmd"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host ""

try {
    Invoke-Expression $Cmd
    $exitCode = $LASTEXITCODE
}
catch {
    $exitCode = 1
    $errorMsg = $_.Exception.Message
    Write-Log "❌ Exception during Maven execution: $errorMsg"
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
if ($exitCode -eq 0) {
    Write-Log "✓ Maven execution completed successfully"
} else {
    Write-Log "❌ Maven execution failed with exit code: $exitCode"
}

Write-Log "--- Script completed, exiting with code $exitCode ---"
exit $exitCode
