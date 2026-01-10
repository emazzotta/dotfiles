$script:MavenCommand = Get-Command mvn -ErrorAction SilentlyContinue | Select-Object -First 1
function mvn {
    if (-not $script:MavenCommand) {
        Write-Error "Maven executable not found in PATH"
        return
    }

    $settingsPaths = @(
        "\\Mac\Home\Projects\private\dotfiles\maven\.m2\settings.xml",
        "$env:USERPROFILE\.m2\settings.xml",
        "$HOME\.m2\settings.xml"
    )

    $settingsFile = $settingsPaths | Where-Object { Test-Path $_ } | Select-Object -First 1

    if ($settingsFile) {
        & $script:MavenCommand.Source -s $settingsFile $args
    } else {
        & $script:MavenCommand.Source $args
    }
}

function Reload-PowerShellModules {
    $modulePath = "$env:USERPROFILE\Documents\WindowsPowerShell\modules"
    if (Test-Path $modulePath) {
        Get-ChildItem -Path $modulePath -Filter "*.ps1" | ForEach-Object {
            Write-Host "Reloading $($_.Name)..." -ForegroundColor Cyan
            Import-Module $_.FullName -Force -Global
        }
        Write-Host "All modules reloaded!" -ForegroundColor Green
    } else {
        Write-Error "PowerShell modules path not found: $modulePath"
    }
}