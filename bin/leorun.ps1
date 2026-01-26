param()

# Manual argument parsing to support both PowerShell (-) and Unix (--) style
$Fast = $false
$Quick = $false
$Help = $false
$Install = ""

$i = 0
while ($i -lt $args.Count) {
    $arg = $args[$i]
    switch -Regex ($arg) {
        '^(-f|--fast)$'      { $Fast = $true }
        '^(-q|--quick)$'     { $Quick = $true }
        '^(-h|--help)$'      { $Help = $true }
        '^(-i|--install)$'   {
            if ($i + 1 -lt $args.Count) {
                $Install = $args[$i + 1]
                $i++
            }
        }
        '^-Fast$'    { $Fast = $true }
        '^-Quick$'   { $Quick = $true }
        '^-Help$'    { $Help = $true }
        '^-Install$' {
            if ($i + 1 -lt $args.Count) {
                $Install = $args[$i + 1]
                $i++
            }
        }
    }
    $i++
}

function Show-Help {
    Write-Host @"
Usage: leorun [OPTIONS]

Run Leonardo with Maven (PowerShell version)

NOTE: Supports both PowerShell-style (-) and Unix-style (--) parameters

OPTIONS:
    -Fast, -f, --fast               Fast mode (exec only, skip clean and compile)
    -Quick, -q, --quick             Quick mode (skip clean, compile + exec)
    -Install, -i, --install PROJECTS Install dependencies before running Leonardo
                                    Format: project1,project2[branch],project3
                                    NOTE: Quote the argument when using brackets
    -Help, -h, --help              Show this help message

EXAMPLES (both styles work):
    leorun                                        Run in normal mode (clean + compile + exec)
    leorun -Fast                                  Run in fast mode (PowerShell style)
    leorun --fast                                 Run in fast mode (Unix style)
    leorun -Install updater,license-manager       Install dependencies (PowerShell style)
    leorun --install "updater[main],license"      Install dependencies (Unix style)
    leorun -i "updater[feature-branch]" -Fast     Install with branch, then fast mode
    leorun --install "updater[main]" --fast       Same using Unix style

"@
}

if ($Help) {
    Show-Help
    exit 0
}

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

    $arguments = @()
    if ($Fast) {
        $arguments += "-Fast"
        Write-Host "   Mode: Fast" -ForegroundColor DarkGray
    }
    elseif ($Quick) {
        $arguments += "-Quick"
        Write-Host "   Mode: Quick" -ForegroundColor DarkGray
    }
    else {
        Write-Host "   Mode: Normal (full build)" -ForegroundColor DarkGray
    }

    if ($Install) {
        $arguments += "-Install"
        $arguments += "`"$Install`""
        Write-Host "   Install: $Install" -ForegroundColor DarkGray
    }

    $argumentString = $arguments -join " "

    $pwshCommand = "pwsh.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" $argumentString"
    Write-Host "   Command: $pwshCommand" -ForegroundColor DarkGray

    try {
        Write-Host "📋 Creating scheduled task 'LeonardoGUI'..." -ForegroundColor Cyan

        $action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-ExecutionPolicy Bypass -File `"$scriptPath`" $argumentString"
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

        Write-Host "⏳ Waiting 1 seconds for task to execute..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 1

        Write-Host "🔍 Checking task execution status..." -ForegroundColor Cyan
        try {
            $taskInfo = Get-ScheduledTaskInfo -TaskName "LeonardoGUI" 2>$null
            if ($taskInfo) {
                Write-Host "   Last run time: $($taskInfo.LastRunTime)" -ForegroundColor DarkGray

                $resultCode = $taskInfo.LastTaskResult
                $isRunning = $resultCode -eq 267009 -or $resultCode -eq 0x41301
                $isSuccess = $resultCode -eq 0

                if ($isSuccess) {
                    Write-Host "   Status: ✓ Completed successfully" -ForegroundColor Green
                }
                elseif ($isRunning) {
                    Write-Host "   Status: ▶️  Currently running (0x$($resultCode.ToString('X')))" -ForegroundColor Green
                    Write-Host "   This is normal - Maven builds can take several minutes" -ForegroundColor DarkGray
                }
                else {
                    Write-Host "   Status: ❌ Error (code: 0x$($resultCode.ToString('X')))" -ForegroundColor Red
                    Write-Host "" -ForegroundColor Yellow
                    Write-Host "   Common causes:" -ForegroundColor DarkGray
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

Write-Host ""
Write-Host "🔄 Syncing with Mac leonardo branch..." -ForegroundColor Cyan
$macLeonardoPath = "\\Mac\Home\Projects\leo-productions\leonardo"

try {
    Push-Location $macLeonardoPath
    $macBranch = git rev-parse --abbrev-ref HEAD 2>$null
    Pop-Location

    if ($macBranch) {
        Write-Host "   Mac branch: $macBranch" -ForegroundColor DarkGray

        Set-Location $LEONARDO_DIR
        $currentBranch = git rev-parse --abbrev-ref HEAD 2>$null

        if ($currentBranch -ne $macBranch) {
            Write-Host "   Current Windows branch: $currentBranch" -ForegroundColor DarkGray
            Write-Host "   🔀 Checking out branch: $macBranch" -ForegroundColor Cyan

            git fetch origin
            git checkout $macBranch

            if ($LASTEXITCODE -eq 0) {
                Write-Host "   ✓ Branch checked out" -ForegroundColor Green
            }
            else {
                Write-Host "   ⚠️  Failed to checkout branch $macBranch" -ForegroundColor Yellow
            }
        }
        else {
            Write-Host "   ✓ Already on branch: $macBranch" -ForegroundColor Green
        }

        Write-Host "   ⬇️  Pulling latest changes..." -ForegroundColor Cyan
        git pull

        if ($LASTEXITCODE -eq 0) {
            Write-Host "   ✓ Latest changes pulled" -ForegroundColor Green
        }
        else {
            Write-Host "   ⚠️  Failed to pull latest changes" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "   ⚠️  Could not determine Mac branch" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "   ⚠️  Could not access Mac leonardo path: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($Install) {
    Write-Host ""
    Write-Host "📦 Processing install dependencies..." -ForegroundColor Cyan

    $gitRemoteUrl = git remote get-url origin 2>$null
    if (-not $gitRemoteUrl) {
        Write-Host "❌ Failed to get git remote origin from leonardo project" -ForegroundColor Red
        exit 1
    }

    $baseGitUrl = $gitRemoteUrl -replace '/leonardo(\.git)?$', ''
    Write-Host "   Base git URL: $baseGitUrl" -ForegroundColor DarkGray

    $projectsDir = Split-Path -Parent $LEONARDO_DIR
    $installProjects = $Install -split ','

    foreach ($projectSpec in $installProjects) {
        $projectSpec = $projectSpec.Trim()

        $projectName = $projectSpec
        $branchName = $null

        if ($projectSpec -match '^(.+?)\[(.+?)\]$') {
            $projectName = $Matches[1]
            $branchName = $Matches[2]
        }

        Write-Host ""
        Write-Host "📦 Processing: $projectName" -ForegroundColor Cyan

        $projectPath = Join-Path $projectsDir $projectName

        if (-not (Test-Path $projectPath)) {
            Write-Host "   ⚠️  Project not found, cloning..." -ForegroundColor Yellow
            $cloneUrl = "$baseGitUrl/$projectName.git"
            Write-Host "   Clone URL: $cloneUrl" -ForegroundColor DarkGray

            try {
                Set-Location $projectsDir
                git clone $cloneUrl
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "   ❌ Failed to clone $projectName" -ForegroundColor Red
                    exit 1
                }
                Write-Host "   ✓ Cloned successfully" -ForegroundColor Green
            }
            catch {
                Write-Host "   ❌ Error cloning: $($_.Exception.Message)" -ForegroundColor Red
                exit 1
            }
        }
        else {
            Write-Host "   ✓ Project exists" -ForegroundColor Green
        }

        Set-Location $projectPath

        if ($branchName) {
            Write-Host "   🔀 Checking out branch: $branchName" -ForegroundColor Cyan
            try {
                git fetch origin
                git checkout $branchName
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "   ❌ Failed to checkout branch $branchName" -ForegroundColor Red
                    exit 1
                }
                Write-Host "   ✓ Branch checked out" -ForegroundColor Green

                Write-Host "   ⬇️  Pulling latest changes..." -ForegroundColor Cyan
                git pull
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "   ❌ Failed to pull latest changes" -ForegroundColor Red
                    exit 1
                }
                Write-Host "   ✓ Latest changes pulled" -ForegroundColor Green
            }
            catch {
                Write-Host "   ❌ Error checking out branch: $($_.Exception.Message)" -ForegroundColor Red
                exit 1
            }
        }
        else {
            $currentBranch = git rev-parse --abbrev-ref HEAD 2>$null
            Write-Host "   ℹ️  Using current branch: $currentBranch" -ForegroundColor DarkGray

            Write-Host "   ⬇️  Pulling latest changes..." -ForegroundColor Cyan
            git pull
            if ($LASTEXITCODE -ne 0) {
                Write-Host "   ❌ Failed to pull latest changes" -ForegroundColor Red
                exit 1
            }
            Write-Host "   ✓ Latest changes pulled" -ForegroundColor Green
        }

        Write-Host "   🔨 Building with Maven..." -ForegroundColor Cyan
        $buildCmd = "mvn clean install -DskipTests -s ops/maven_settings.xml"
        Write-Host "   Command: $buildCmd" -ForegroundColor DarkGray

        try {
            Invoke-Expression $buildCmd
            if ($LASTEXITCODE -ne 0) {
                Write-Host "   ❌ Maven build failed for $projectName" -ForegroundColor Red
                exit 1
            }
            Write-Host "   ✓ Build completed successfully" -ForegroundColor Green
        }
        catch {
            Write-Host "   ❌ Error during build: $($_.Exception.Message)" -ForegroundColor Red
            exit 1
        }
    }

    Set-Location $LEONARDO_DIR
    Write-Host ""
    Write-Host "✓ All install dependencies processed" -ForegroundColor Green
}

$MvnSettingsFlag = "-s ops/maven_settings.xml"
$MvnRunCmd = "mvn exec:exec -Prun-leonardo -DskipTests $MvnSettingsFlag -pl leonardo-leonardo"

$Mode = "normal"
if ($Fast) { $Mode = "fast" }
elseif ($Quick) { $Mode = "quick" }

Write-Host ""
Write-Host "🚀 Preparing Maven execution..." -ForegroundColor Cyan
Write-Host "   Mode: $Mode" -ForegroundColor Yellow

switch ($Mode) {
    "fast" {
        Write-Host "   Skip: clean, install (exec only)" -ForegroundColor DarkGray
        $Cmd = $MvnRunCmd
    }
    "quick" {
        Write-Host "   Skip: clean (compile + exec)" -ForegroundColor DarkGray
        $Cmd = "mvn $MvnSettingsFlag -DskipTests compile && $MvnRunCmd"
    }
    default {
        Write-Host "   Full build: clean + install + exec" -ForegroundColor DarkGray
        $Cmd = "mvn $MvnSettingsFlag -DskipTests clean install && $MvnRunCmd"
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
