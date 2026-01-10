function Connect-LeonardoVPN {
    param(
        [switch]$Disconnect,
        [switch]$Status,
        [string]$Username,
        [string]$Password
    )

    $VpnName = "LeonardoVPN"

    if ($Status) {
        $connection = Get-VpnConnection -Name $VpnName -ErrorAction SilentlyContinue
        if ($connection) {
            Write-Host "VPN Status: $($connection.ConnectionStatus)" -ForegroundColor $(if ($connection.ConnectionStatus -eq "Connected") { "Green" } else { "Yellow" })
        } else {
            Write-Host "VPN '$VpnName' not found" -ForegroundColor Red
        }
        return
    }

    if ($Disconnect) {
        Write-Host "Disconnecting from $VpnName..." -ForegroundColor Yellow
        rasdial $VpnName /disconnect
        return
    }

    Write-Host "Connecting to $VpnName..." -ForegroundColor Cyan

    if ($Username -and $Password) {
        rasdial $VpnName $Username $Password
    } else {
        rasdial $VpnName
    }
}
