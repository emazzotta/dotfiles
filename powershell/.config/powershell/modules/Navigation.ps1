function Get-LongListing {
    Get-ChildItem -Path . -Force | Sort-Object LastWriteTime -Descending | Format-Table -AutoSize
}

function ..1 { cd .. }
function ..2 { cd ..; cd .. }
function ..3 { cd ..; cd ..; cd .. }
function ..4 { cd ..; cd ..; cd ..; cd .. }

function l {
    $ESC = [char]27
    Write-Host "$ESC[2J$ESC[H" -NoNewline
}

function Navigate-MacHome {
    Set-Location \\Mac\Home
}