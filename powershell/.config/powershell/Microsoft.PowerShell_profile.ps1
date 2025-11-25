oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH/spaceship.omp.json" | Invoke-Expression

Set-Alias -Name l -Value Clear-Host

function Get-LongListing {
    Get-ChildItem -Path . -Force | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize
}
Set-Alias -Name ll -Value Get-LongListing

function ..1 { cd .. }
function ..2 { cd ..; cd .. }
function ..3 { cd ..; cd ..; cd .. }
function ..4 { cd ..; cd ..; cd ..; cd .. }

function Connect-Devserver-VM {
    # $ Enter-PSSession -HostName devserver.leonardo.local -UserName "LEONARDO\Administrator" -SSHTransport -Port 2222
    $CustomProfilePath = "C:\Users\administrator.LEONARDO\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
    $session = New-PSSession -HostName devserver.leonardo.local -UserName "administrator" -SSHTransport -Port 2222
    Invoke-Command -Session $session -ScriptBlock {
        param($ProfilePath)
        Set-Location ~
        if (Test-Path $ProfilePath) {
            . $ProfilePath
        } else {
            Write-Host "Profile path not found: $ProfilePath"
        }
    } -ArgumentList $CustomProfilePath
    Enter-PSSession -Session $session
}

function Connect-Devhost-VM {
    # $ Enter-PSSession -HostName 192.168.192.150 -UserName "dev-server\administrator" -SSHTransport -Port 2222
    # # Copy your public key to the other server
    # $ Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ... your_key_here"
    $CustomProfilePath = "C:\Users\Administrator\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
    $session = New-PSSession -HostName 192.168.192.150 -UserName "administrator" -SSHTransport -Port 2222
    Invoke-Command -Session $session -ScriptBlock {
        param($ProfilePath)
        Set-Location ~
        if (Test-Path $ProfilePath) {
            . $ProfilePath
        } else {
            Write-Host "Profile path not found: $ProfilePath"
        }
    } -ArgumentList $CustomProfilePath
    Enter-PSSession -Session $session
}

Set-Alias -Name wdev -Value Connect-Devserver-VM
Set-Alias -Name whost -Value Connect-Devhost-VM
