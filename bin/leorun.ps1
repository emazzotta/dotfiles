param(
    [switch]$Fast,
    [switch]$f
)

$ErrorActionPreference = "Stop"

$SKIP_COMPILE = $Fast -or $f
$MAVEN_SETTINGS = "\\Mac\Home\Projects\private\dotfiles\maven\.m2\settings.xml"

$env:LEONARDO_PROJECTS = "C:\Users\emanuelemazzotta\ProjectsWindows"
$LEONARDO_DIR = "$env:LEONARDO_PROJECTS\leonardo"
$RESOURCES_DIR = "$env:LEONARDO_PROJECTS\leonardo\leonardo-resources"
$MAIN_CLASS = "ifactory.leonardo.model.LeonardoApplication"

function Change-Dir($Path) {
    Write-Host "📁 Changing to: $Path" -ForegroundColor Cyan
    Set-Location $Path
}

Write-Host "🚀 Starting Leonardo build and run..." -ForegroundColor Green
Write-Host "📂 Work directory: $env:LEONARDO_PROJECTS"
Write-Host "☕ Main class: $MAIN_CLASS"
Write-Host ""

if (-not $SKIP_COMPILE) {
    Write-Host "🔨 Building Leonardo..." -ForegroundColor Cyan
    Change-Dir $LEONARDO_DIR
    mvn -s $MAVEN_SETTINGS clean compile -DskipTests
} else {
    Write-Host "⚡ Skipping compilation (fast mode)" -ForegroundColor Magenta
    Change-Dir $LEONARDO_DIR
}

git pull

Write-Host "▶️  Starting Leonardo application..." -ForegroundColor Green
Change-Dir $RESOURCES_DIR
mvn -s $MAVEN_SETTINGS -f "$LEONARDO_DIR\pom.xml" exec:java -pl leonardo-leonardo "-Dexec.mainClass=$MAIN_CLASS" "-Dlog4j2.rootLevel=INFO"

Write-Host "✅ Leonardo startup complete!" -ForegroundColor Green
