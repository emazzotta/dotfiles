param(
    [switch]$Fast,
    [switch]$f,
    [switch]$Quick,
    [switch]$q
)

$ErrorActionPreference = "Stop"

$SKIP_COMPILE = $Fast -or $f
$QUICK_COMPILE = $Quick -or $q
$MAVEN_SETTINGS = "\\Mac\Home\Projects\private\dotfiles\maven\.m2\settings.xml"
$env:MAVEN_OPTS = '-Djava.awt.headless=false -Dlog4j2.rootLevel=DEBUG'

$env:LEONARDO_PROJECTS = "C:\Users\emanuelemazzotta\ProjectsWindows"
$LEONARDO_DIR = "$env:LEONARDO_PROJECTS\leonardo"
$RESOURCES_DIR = "$env:LEONARDO_PROJECTS\leonardo\leonardo-resources"
$MAIN_CLASS = "ifactory.leonardo.model.LeonardoApplication"
$SOURCE_LEONARDO_DIR = "\\Mac\Home\Projects\leo-productions\leonardo"

function Change-Dir($Path) {
    Write-Host "📁 Changing to: $Path" -ForegroundColor Cyan
    Set-Location $Path
}

$isSSH = $env:SSH_CONNECTION -or $env:SSH_CLIENT

if ($isSSH) {
    Write-Host "🔗 SSH detected - launching in Windows GUI session via Task Scheduler..." -ForegroundColor Yellow

    $scriptPath = $MyInvocation.MyCommand.Path
    $fastArg = if ($SKIP_COMPILE) { "-Fast" } elseif ($QUICK_COMPILE) { "-Quick" } else { "" }
    $command = "Set-Location '$PSScriptRoot'; & '$scriptPath' $fastArg"

    $action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$command`""
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances Parallel

    Register-ScheduledTask -TaskName "LeonardoGUI" -Action $action -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "LeonardoGUI"
    Write-Host "✅ Task started. GUI will appear in Parallels window." -ForegroundColor Green

    Start-Sleep -Seconds 3
    Unregister-ScheduledTask -TaskName "LeonardoGUI" -Confirm:$false -ErrorAction SilentlyContinue
    exit 0
}

Write-Host "🚀 Starting Leonardo build and run..." -ForegroundColor Green
Write-Host "📂 Work directory: $env:LEONARDO_PROJECTS"
Write-Host "☕ Main class: $MAIN_CLASS"
Write-Host ""

Write-Host "🔍 Detecting branch from source repository..." -ForegroundColor Cyan
Push-Location $SOURCE_LEONARDO_DIR
$sourceBranch = git rev-parse --abbrev-ref HEAD
Pop-Location
Write-Host "📌 Source branch: $sourceBranch" -ForegroundColor Green

Change-Dir $LEONARDO_DIR
Write-Host "🔄 Checking out branch: $sourceBranch" -ForegroundColor Cyan
git checkout $sourceBranch
git pull

if ($QUICK_COMPILE) {
    Write-Host "⚡ Quick incremental compile (no clean)..." -ForegroundColor Yellow
    mvn -s $MAVEN_SETTINGS compile -DskipTests
} elseif (-not $SKIP_COMPILE) {
    Write-Host "🔨 Full clean compile..." -ForegroundColor Cyan
    mvn -s $MAVEN_SETTINGS clean compile -DskipTests
} else {
    Write-Host "⏭️  Skipping compilation entirely" -ForegroundColor Magenta
}

Write-Host "▶️  Starting Leonardo application..." -ForegroundColor Green
Change-Dir $RESOURCES_DIR
mvn -s $MAVEN_SETTINGS -f "$LEONARDO_DIR\pom.xml" exec:java -pl leonardo-leonardo "-Dexec.mainClass=$MAIN_CLASS"
