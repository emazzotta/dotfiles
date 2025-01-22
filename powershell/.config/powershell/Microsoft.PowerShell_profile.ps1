oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH\spaceship.omp.json" | Invoke-Expression

function Get-LongListing {
    Get-ChildItem -Path . -Force | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize
}

function Connect-VM {
    Enter-PSSession -HostName devserver.leonardo.local -UserName "LEONARDO\Administrator" -SSHTransport -Port 2222
}

Set-Alias -Name l -Value Clear-Host
Set-Alias -Name ll -Value Get-LongListing
Set-Alias -Name vm -Value Connect-VM
