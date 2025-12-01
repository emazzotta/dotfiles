$script:MavenCommand = Get-Command mvn -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1

function mvn {
    if ($script:MavenCommand) {
        & $script:MavenCommand.Source -s "\\Mac\Home\Projects\private\dotfiles\maven\.m2\settings.xml" $args
    } else {
        Write-Error "Maven executable not found in PATH"
    }
}
