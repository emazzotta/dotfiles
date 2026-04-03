param()

$Fast = $false
$Quick = $false
$Help = $false
$Install = ""

$i = 0
while ($i -lt $args.Count) {
    $arg = $args[$i]
    switch -Regex ($arg) {
        '^(-f|--fast|-Fast)$'    { $Fast = $true }
        '^(-q|--quick|-Quick)$'  { $Quick = $true }
        '^(-h|--help|-Help)$'    { $Help = $true }
        '^(-i|--install|-Install)$' {
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

OPTIONS:
    -Fast, -f, --fast               Fast mode (exec only, skip clean and compile)
    -Quick, -q, --quick             Quick mode (skip clean, compile + exec)
    -Install, -i, --install PROJECTS Install dependencies before running Leonardo
                                    Format: project1,project2[branch],project3
                                    NOTE: Quote the argument when using brackets
    -Help, -h, --help              Show this help message

EXAMPLES:
    leorun                                        Run in normal mode (clean + compile + exec)
    leorun -Fast                                  Run in fast mode
    leorun --fast                                 Run in fast mode
    leorun -Install updater,license-manager       Install dependencies
    leorun -i "updater[feature-branch]" -Fast     Install with branch, then fast mode

"@
}

if ($Help) {
    Show-Help
    exit 0
}

$CommonsSettings = "commons/configs/maven_settings.xml"

function Test-GitCrypted {
    param([string]$FilePath)
    $bytes = [System.IO.File]::ReadAllBytes($FilePath)
    if ($bytes.Length -lt 9) { return $false }
    $header = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 9)
    return $header -match "GITCRYPT"
}

function Resolve-SettingsFlag {
    param([string]$ProjectDir)
    $settingsPath = Join-Path $ProjectDir $CommonsSettings
    if ((Test-Path $settingsPath) -and -not (Test-GitCrypted $settingsPath)) {
        return "-s $CommonsSettings"
    }
    return ""
}

function Sync-GitBranch {
    param(
        [string]$ProjectPath,
        [string]$BranchName = ""
    )

    Set-Location $ProjectPath

    if ($BranchName) {
        Write-Host "   Checking out branch: $BranchName" -ForegroundColor Cyan
        git fetch origin
        git checkout $BranchName
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   Failed to checkout branch $BranchName" -ForegroundColor Red
            exit 1
        }
    } else {
        $currentBranch = git rev-parse --abbrev-ref HEAD 2>$null
        Write-Host "   Using current branch: $currentBranch" -ForegroundColor DarkGray
    }

    Write-Host "   Pulling latest changes..." -ForegroundColor Cyan
    git pull
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   Failed to pull latest changes" -ForegroundColor Red
        exit 1
    }
}

function Install-Project {
    param(
        [string]$ProjectSpec,
        [string]$ProjectsDir,
        [string]$BaseGitUrl
    )

    $ProjectSpec = $ProjectSpec.Trim()
    $projectName = $ProjectSpec
    $branchName = $null

    if ($ProjectSpec -match '^(.+?)\[(.+?)\]$') {
        $projectName = $Matches[1]
        $branchName = $Matches[2]
    }

    Write-Host ""
    Write-Host "Processing: $projectName" -ForegroundColor Cyan

    $projectPath = Join-Path $ProjectsDir $projectName

    if (-not (Test-Path $projectPath)) {
        Write-Host "   Project not found, cloning..." -ForegroundColor Yellow
        $cloneUrl = "$BaseGitUrl/$projectName.git"
        Write-Host "   Clone URL: $cloneUrl" -ForegroundColor DarkGray

        Set-Location $ProjectsDir
        git clone $cloneUrl
        if ($LASTEXITCODE -ne 0) {
            Write-Host "   Failed to clone $projectName" -ForegroundColor Red
            exit 1
        }
    }

    Sync-GitBranch -ProjectPath $projectPath -BranchName $branchName

    Write-Host "   Building with Maven..." -ForegroundColor Cyan
    $settingsFlag = Resolve-SettingsFlag -ProjectDir $projectPath
    $buildCmd = "mvn clean install -DskipTests $settingsFlag"
    Write-Host "   Command: $buildCmd" -ForegroundColor DarkGray

    Invoke-Expression $buildCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   Maven build failed for $projectName" -ForegroundColor Red
        exit 1
    }
    Write-Host "   Build completed" -ForegroundColor Green
}

$logFile = "$env:TEMP\leorun.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Write-Log {
    param([string]$Message)
    "$timestamp - $Message" | Out-File -FilePath $logFile -Append -Encoding UTF8
    Write-Host $Message
}

$ErrorActionPreference = "Stop"

Write-Log "Starting leorun.ps1..."

$isSSH = $env:SSH_CONNECTION -or $env:SSH_CLIENT

if ($isSSH) {
    Write-Log "SSH session detected - creating scheduled task for interactive session"

    $scriptPath = $MyInvocation.MyCommand.Path

    $isNetworkPath = $scriptPath -match "^\\\\[^\\]+"
    if ($isNetworkPath) {
        $localScriptPath = "$env:TEMP\leorun_temp.ps1"
        try {
            Copy-Item -Path $scriptPath -Destination $localScriptPath -Force
            $scriptPath = $localScriptPath
        } catch {
            Write-Host "   Failed to copy script locally: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    $arguments = @()
    if ($Fast) { $arguments += "-Fast" }
    elseif ($Quick) { $arguments += "-Quick" }
    if ($Install) { $arguments += "-Install"; $arguments += "`"$Install`"" }

    $argumentString = $arguments -join " "
    $pwshArgs = "-ExecutionPolicy Bypass -File `"$scriptPath`" $argumentString"

    try {
        $action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument $pwshArgs
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -Hidden:$false `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2)

        Register-ScheduledTask -TaskName "LeonardoGUI" -Action $action -Principal $principal -Settings $settings -Force | Out-Null
        Start-ScheduledTask -TaskName "LeonardoGUI"

        Start-Sleep -Seconds 1

        try {
            $taskInfo = Get-ScheduledTaskInfo -TaskName "LeonardoGUI" 2>$null
            if ($taskInfo) {
                $resultCode = $taskInfo.LastTaskResult
                $isRunning = $resultCode -eq 267009 -or $resultCode -eq 0x41301
                if ($resultCode -eq 0) {
                    Write-Host "   Status: Completed successfully" -ForegroundColor Green
                } elseif ($isRunning) {
                    Write-Host "   Status: Running (Maven builds can take several minutes)" -ForegroundColor Green
                } else {
                    Write-Host "   Status: Error (code: 0x$($resultCode.ToString('X')))" -ForegroundColor Red
                }
            }
        } catch {}

        Unregister-ScheduledTask -TaskName "LeonardoGUI" -Confirm:$false

        if ($isNetworkPath -and (Test-Path $localScriptPath)) {
            Remove-Item $localScriptPath -Force -ErrorAction SilentlyContinue
        }

        Write-Host ""
        Write-Host "Leonardo should now be starting in an interactive session on your desktop" -ForegroundColor Green
        Write-Host "Log: $logFile" -ForegroundColor DarkGray
        exit 0
    } catch {
        Write-Host "Error during scheduled task execution: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

Write-Log "Running directly - proceeding with normal execution"

$env:LEONARDO_PROJECTS = "C:\Users\emanuelemazzotta\ProjectsWindows"
$LEONARDO_DIR = "$env:LEONARDO_PROJECTS\leonardo"

if (-not (Test-Path "$LEONARDO_DIR/pom.xml")) {
    Write-Host "Error: Leonardo project not found (missing pom.xml in $LEONARDO_DIR)" -ForegroundColor Red
    exit 1
}

Set-Location $LEONARDO_DIR
Write-Host "Running from: $LEONARDO_DIR" -ForegroundColor Cyan

Write-Host ""
Write-Host "Syncing with Mac leonardo branch..." -ForegroundColor Cyan
$macLeonardoPath = "\\Mac\Home\Projects\leo-productions\leonardo"

try {
    Push-Location $macLeonardoPath
    $macBranch = git rev-parse --abbrev-ref HEAD 2>$null
    Pop-Location

    if ($macBranch) {
        Set-Location $LEONARDO_DIR
        $currentBranch = git rev-parse --abbrev-ref HEAD 2>$null

        if ($currentBranch -ne $macBranch) {
            Write-Host "   Switching from $currentBranch to $macBranch" -ForegroundColor Cyan
            git fetch origin
            git checkout $macBranch
        } else {
            Write-Host "   Already on branch: $macBranch" -ForegroundColor Green
        }

        git pull
    }
} catch {
    Write-Host "   Could not access Mac leonardo path: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($Install) {
    Write-Host ""
    Write-Host "Processing install dependencies..." -ForegroundColor Cyan

    $gitRemoteUrl = git remote get-url origin 2>$null
    if (-not $gitRemoteUrl) {
        Write-Host "Failed to get git remote origin" -ForegroundColor Red
        exit 1
    }

    $baseGitUrl = $gitRemoteUrl -replace '/leonardo(\.git)?$', ''
    $projectsDir = Split-Path -Parent $LEONARDO_DIR

    foreach ($projectSpec in ($Install -split ',')) {
        Install-Project -ProjectSpec $projectSpec -ProjectsDir $projectsDir -BaseGitUrl $baseGitUrl
    }

    Set-Location $LEONARDO_DIR
    Write-Host ""
    Write-Host "All install dependencies processed" -ForegroundColor Green
}

$MvnSettingsFlag = Resolve-SettingsFlag -ProjectDir $LEONARDO_DIR
$MvnRun = "mvn exec:exec -Prun-leonardo -DskipTests $MvnSettingsFlag -pl leonardo-leonardo"

$Mode = if ($Fast) { "fast" } elseif ($Quick) { "quick" } else { "normal" }

Write-Host ""
Write-Host "Mode: $Mode" -ForegroundColor Yellow

switch ($Mode) {
    "fast" {
        Write-Log "[$Mode] $MvnRun"
        Invoke-Expression $MvnRun
    }
    "quick" {
        Write-Log "[$Mode] mvn compile + exec"
        Invoke-Expression "mvn $MvnSettingsFlag -DskipTests compile"
        if ($LASTEXITCODE -eq 0) { Invoke-Expression $MvnRun }
    }
    default {
        Write-Log "[normal] mvn clean install + exec"
        Invoke-Expression "mvn $MvnSettingsFlag -DskipTests clean install"
        if ($LASTEXITCODE -eq 0) { Invoke-Expression $MvnRun }
    }
}

$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Log "Maven execution completed successfully"
} else {
    Write-Log "Maven execution failed with exit code: $exitCode"
}

exit $exitCode
