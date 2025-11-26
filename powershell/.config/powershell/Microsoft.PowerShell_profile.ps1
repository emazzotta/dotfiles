$profileDir = if ($PROFILE) {
    Split-Path -Parent $PROFILE
} else {
    Split-Path -Parent $PSCommandPath
}

$modulesPath = Join-Path $profileDir "modules"

if (Test-Path $modulesPath) {
    Get-ChildItem -Path $modulesPath -Filter "*.ps1" | ForEach-Object {
        . $_.FullName
    }
}
