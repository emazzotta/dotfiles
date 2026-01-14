function Reload-Profile {
    $profilePath = "$env:USERPROFILE\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
    if (Test-Path $profilePath) {
        Write-Host "Reloading PowerShell profile..." -ForegroundColor Cyan
        . $profilePath
    } else {
        Write-Error "Profile not found at: $profilePath"
    }
}

function Exit-Session {
    if (Get-PSSession -ErrorAction SilentlyContinue) {
        Exit-PSSession
    }
    exit
}

function leorun {
    & \\Mac\Home\Projects\private\dotfiles\bin\leorun.ps1 @args
}
