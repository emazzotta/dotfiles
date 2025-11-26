oh-my-posh init pwsh --config "$env:POSH_THEMES_PATH/spaceship.omp.json" | Invoke-Expression

function Get-LongListing {
    Get-ChildItem -Path . -Force | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize
}

function ..1 { cd .. }
function ..2 { cd ..; cd .. }
function ..3 { cd ..; cd ..; cd .. }
function ..4 { cd ..; cd ..; cd ..; cd .. }


### X11 ###

# choco install -y VcXsrv
# choco install -y xming

# Must be before 'Match Group administrators'!
# Add-Content -Path "C:\ProgramData\ssh\sshd_config" -Value "X11Forwarding yes"
# Add-Content -Path "C:\ProgramData\ssh\sshd_config" -Value "X11DisplayOffset 10"
# Add-Content -Path "C:\ProgramData\ssh\sshd_config" -Value "X11UseLocalhost no"
# Add-Content -Path "C:\ProgramData\ssh\sshd_config" -Value 'XAuthLocation "C:/Program Files/VcXsrv/xauth.exe"'

# $env:DISPLAY = "10.211.55.2:0"
# $env:DISPLAY= "127.0.0.1:0.0"
$vcxsrvPath = "C:\Program Files\VcXsrv"
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";$vcxsrvPath", [EnvironmentVariableTarget]::Machine)
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# on Windows: Start "XLaunch"
# on macOS: $ xhost + 10.211.55.3
if (Get-Command Get-NetRoute -ErrorAction SilentlyContinue) {
    $macIP = (Get-NetRoute -DestinationPrefix "0.0.0.0/0").NextHop | Select-Object -First 1
    $env:DISPLAY = "${macIP}:0"
}
###########

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
    # $ Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCvASgx7DXcBlrum0v7rEBKPOeSrRkhPBFvtp+SU8tCWIsrMCqiYKKe78r2jiD8UEVbz/GDvncWFvJwR6hohCQf0UvCXWmDnobbr2vgYdRpCh+6TvcjlJYFJZMZ1w+dLrQP/W6cQNr99H05tQYx8pK3hXDojV9M2wT3CH3XSO44C6QcKJuwSK0kaYFeVn/CbPhYSc+Tl37ecIwzi16WVLd2cMWgxt0BGb4jYF2VfjvYQ5HE4b2yTr9h597bmUa2e2cNmKj2kzjHDlCMrDlaGHiYhvAJR6RnJ4EtdOYBjJbIib1Rqbw+EWUnA8nQqI2BrSMlSbisHjEELA1ST8ejMyxZ Emanuele@MacBookPro"
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

function Connect-Parallels-VM {
    # $ Enter-PSSession -HostName 10.211.55.3 -UserName "emanuelemazzotta" -SSHTransport -Port 22
    # # Copy your public key to the other server
    # $ Add-Content -Path C:\ProgramData\ssh\administrators_authorized_keys -Value "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCvASgx7DXcBlrum0v7rEBKPOeSrRkhPBFvtp+SU8tCWIsrMCqiYKKe78r2jiD8UEVbz/GDvncWFvJwR6hohCQf0UvCXWmDnobbr2vgYdRpCh+6TvcjlJYFJZMZ1w+dLrQP/W6cQNr99H05tQYx8pK3hXDojV9M2wT3CH3XSO44C6QcKJuwSK0kaYFeVn/CbPhYSc+Tl37ecIwzi16WVLd2cMWgxt0BGb4jYF2VfjvYQ5HE4b2yTr9h597bmUa2e2cNmKj2kzjHDlCMrDlaGHiYhvAJR6RnJ4EtdOYBjJbIib1Rqbw+EWUnA8nQqI2BrSMlSbisHjEELA1ST8ejMyxZ Emanuele@MacBookPro"
    $DotfilesProfilePath = "\\Mac\Home\Projects\private\dotfiles\powershell\.config\powershell\Microsoft.PowerShell_profile.ps1"
    $CustomProfilePath = "C:\Users\emanuelemazzotta\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"
    $session = New-PSSession -HostName 10.211.55.3 -UserName "emanuelemazzotta" -SSHTransport -Port 22
    Invoke-Command -Session $session -ScriptBlock {
        param($SourcePath, $DestPath)
        Set-Location ~
        $destDir = Split-Path -Parent $DestPath
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        if (Test-Path $SourcePath) {
            Copy-Item -Path $SourcePath -Destination $DestPath -Force
            Write-Host "Profile copied from $SourcePath to $DestPath"
        } else {
            Write-Host "Source profile not found: $SourcePath"
        }
        if (Test-Path $DestPath) {
            . $DestPath
            Write-Host "Profile loaded successfully"
        }
        Write-Host "DISPLAY is set to: $env:DISPLAY"
    } -ArgumentList $DotfilesProfilePath, $CustomProfilePath
    Enter-PSSession -Session $session
}

function Set-Up-SSH-Access {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    Start-Service sshd
    Set-Service -Name sshd -StartupType 'Automatic'
    New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
    # Check ip via ipconfig
    choco install powershell-core -y
    Add-Content -Path "C:\ProgramData\ssh\sshd_config" -Value 'Subsystem powershell "C:/Program Files/PowerShell/7/pwsh.exe" -sshs -NoLogo -NoProfile'
    Restart-Service sshd

}

function leorun {
    & \\Mac\Home\Projects\private\dotfiles\bin\leorun.ps1 @args
}

function Run-Interactive {
    # choco install -y sysinternals
    param([string]$Command)
    PsExec.exe -i -d pwsh -Command $Command
}

Set-Alias -Name wdev -Value Connect-Devserver-VM
Set-Alias -Name wd -Value Connect-Devserver-VM

Set-Alias -Name whost -Value Connect-Devhost-VM
Set-Alias -Name wh -Value Connect-Devhost-VM

Set-Alias -Name wlocal -Value Connect-Parallels-VM
Set-Alias -Name wl -Value Connect-Parallels-VM

Set-Alias -Name l -Value Clear-Host
Set-Alias -Name ll -Value Get-LongListing
Set-Alias -Name e -Value Exit-PSSession
