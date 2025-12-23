function Sync-ProfileAndModules {
    param(
        [Parameter(Mandatory=$true)]
        [System.Management.Automation.Runspaces.PSSession]$Session,
        [Parameter(Mandatory=$true)]
        [string]$SourceProfilePath,
        [Parameter(Mandatory=$true)]
        [string]$DestProfilePath
    )

    Invoke-Command -Session $Session -ScriptBlock {
        param($SourceProfile, $DestProfile)

        function Copy-IfDifferent {
            param($Source, $Dest)

            if (-not (Test-Path $Source)) {
                return $false
            }

            $shouldCopy = $false

            if (-not (Test-Path $Dest)) {
                $shouldCopy = $true
            } else {
                $sourceHash = (Get-FileHash $Source -Algorithm MD5).Hash
                $destHash = (Get-FileHash $Dest -Algorithm MD5).Hash
                if ($sourceHash -ne $destHash) {
                    $shouldCopy = $true
                }
            }

            if ($shouldCopy) {
                $destDir = Split-Path -Parent $Dest
                if (-not (Test-Path $destDir)) {
                    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
                }
                Copy-Item -Path $Source -Destination $Dest -Force
                return $true
            }
            return $false
        }

        Set-Location ~

        $copiedCount = 0
        $deletedCount = 0

        if (Copy-IfDifferent $SourceProfile $DestProfile) {
            $copiedCount++
            Write-Host "✅ Profile copied: $(Split-Path -Leaf $DestProfile)" -ForegroundColor Green
        }

        $sourceModulesDir = Join-Path (Split-Path -Parent $SourceProfile) "modules"
        $destModulesDir = Join-Path (Split-Path -Parent $DestProfile) "modules"

        if (Test-Path $sourceModulesDir) {
            if (-not (Test-Path $destModulesDir)) {
                New-Item -ItemType Directory -Path $destModulesDir -Force | Out-Null
            }

            $sourceModuleFiles = Get-ChildItem -Path $sourceModulesDir -Filter "*.ps1" -ErrorAction SilentlyContinue
            $sourceModuleNames = $sourceModuleFiles | ForEach-Object { $_.Name }

            foreach ($moduleFile in $sourceModuleFiles) {
                $destModulePath = Join-Path $destModulesDir $moduleFile.Name
                if (Copy-IfDifferent $moduleFile.FullName $destModulePath) {
                    $copiedCount++
                    Write-Host "✅ Module copied: $($moduleFile.Name)" -ForegroundColor Green
                }
            }

            $destModuleFiles = Get-ChildItem -Path $destModulesDir -Filter "*.ps1" -ErrorAction SilentlyContinue
            foreach ($destModule in $destModuleFiles) {
                if ($destModule.Name -notin $sourceModuleNames) {
                    Remove-Item $destModule.FullName -Force
                    $deletedCount++
                    Write-Host "🗑️  Module deleted: $($destModule.Name)" -ForegroundColor Gray
                }
            }
        }

        if ($copiedCount -eq 0 -and $deletedCount -eq 0) {
            Write-Host "✓ All files up to date" -ForegroundColor Gray
        } else {
            if ($copiedCount -gt 0) {
                Write-Host "✅ Synced $copiedCount file(s)" -ForegroundColor Green
            }
            if ($deletedCount -gt 0) {
                Write-Host "🗑️  Deleted $deletedCount obsolete file(s)" -ForegroundColor Gray
            }
        }

        if (Test-Path $DestProfile) {
            try {
                . $DestProfile
                Write-Host "✅ Profile loaded" -ForegroundColor Green
            } catch {
                Write-Host "⚠️  Error loading profile: $_" -ForegroundColor Yellow
            }
        }

    } -ArgumentList $SourceProfilePath, $DestProfilePath
}

function Connect-Devhost-VM {
    $DotfilesProfilePath = "\\Mac\Home\Projects\private\dotfiles\powershell\.config\powershell\Microsoft.PowerShell_profile.ps1"
    $CustomProfilePath = "C:\Users\Administrator\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"

    $session = New-PSSession -HostName 192.168.192.150 -UserName "administrator" -SSHTransport -Port 2222
    Sync-ProfileAndModules -Session $session -SourceProfilePath $DotfilesProfilePath -DestProfilePath $CustomProfilePath
    Enter-PSSession -Session $session
}

function Connect-Parallels-VM {
    $DotfilesProfilePath = "\\Mac\Home\Projects\private\dotfiles\powershell\.config\powershell\Microsoft.PowerShell_profile.ps1"
    $CustomProfilePath = "C:\Users\emanuelemazzotta\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1"

    $session = New-PSSession -HostName 10.211.55.3 -UserName "emanuelemazzotta" -SSHTransport -Port 22
    Sync-ProfileAndModules -Session $session -SourceProfilePath $DotfilesProfilePath -DestProfilePath $CustomProfilePath
    Enter-PSSession -Session $session
}

function Set-Up-SSH-Access {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    Start-Service sshd
    Set-Service -Name sshd -StartupType 'Automatic'
    New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
    choco install powershell-core -y
    Add-Content -Path "C:\ProgramData\ssh\sshd_config" -Value 'Subsystem powershell "C:/Program Files/PowerShell/7/pwsh.exe" -sshs -NoLogo -NoProfile'
    Restart-Service sshd
}
