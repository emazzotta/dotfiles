function Remove-ReadOnly {
    param([Parameter(Mandatory=$true)][string]$Path)
    Set-ItemProperty $Path -Name IsReadOnly -Value $false
    Remove-Item $Path -Force
}

function Start-InGUI {
    if ($args.Count -eq 0) {
        Write-Host "Usage: gui <command> [arguments...]" -ForegroundColor Yellow
        return
    }
    $executable = $args[0]
    $resolvedArgs = @()
    for ($i = 1; $i -lt $args.Count; $i++) {
        $arg = $args[$i]
        if (Test-Path $arg -ErrorAction SilentlyContinue) {
            $resolvedArgs += (Resolve-Path $arg).Path
        } else {
            $resolvedArgs += $arg
        }
    }
    $arguments = $resolvedArgs -join ' '
    $action = New-ScheduledTaskAction -Execute $executable -Argument $arguments -WorkingDirectory $PWD
    $principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName "StartInGUI" -Action $action -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName "StartInGUI"
    Start-Sleep 2
    Unregister-ScheduledTask -TaskName "StartInGUI" -Confirm:$false
}

function leorun {
    & \\Mac\Home\Projects\private\dotfiles\bin\leorun.ps1 @args
}
