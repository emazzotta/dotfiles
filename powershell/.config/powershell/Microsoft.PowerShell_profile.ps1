oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH\spaceship.omp.json" | Invoke-Expression

Set-Alias -Name l -Value Clear-Host

function Get-LongListing {
    Get-ChildItem -Path . -Force | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize
}
Set-Alias -Name ll -Value Get-LongListing

#######

#function Connect-VM {
#    Enter-PSSession -HostName devserver.leonardo.local -UserName "LEONARDO\Administrator" -SSHTransport -Port 2222
#}

function Connect-VM {
    $CustomProfilePath = "C:\Users\administrator.LEONARDO\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
    $session = New-PSSession -HostName devserver.leonardo.local -UserName "LEONARDO\Administrator" -SSHTransport -Port 2222
    Invoke-Command -Session $session -ScriptBlock {
        param($ProfilePath)
        if (Test-Path $ProfilePath) {
            . $ProfilePath
        } else {
            Write-Host "Profile path not found: $ProfilePath"
        }
    } -ArgumentList $CustomProfilePath
    Enter-PSSession -Session $session
}

Set-Alias -Name vm -Value Connect-VM
