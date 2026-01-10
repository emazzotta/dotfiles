function Reload-Profile {
    $profilePath = "$env:USERPROFILE\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
    if (Test-Path $profilePath) {
        Write-Host "Reloading PowerShell profile..." -ForegroundColor Cyan
        $content = Get-Content $profilePath -Raw
        Invoke-Expression $content
    } else {
        Write-Error "Profile not found at: $profilePath"
    }
}
