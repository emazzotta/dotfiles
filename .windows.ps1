#!/usr/bin/env pwsh

# Set directory for installation - Chocolatey does not lock
# down the directory if not the default
$InstallDir='C:\ProgramData\chocoportable'
$env:ChocolateyInstall="$InstallDir"

# If your PowerShell Execution policy is restrictive, you may
# not be able to get around that. Try setting your session to
# Bypass.
Set-ExecutionPolicy Bypass -Scope Process -Force;

# All install options - offline, proxy, etc at
# https://chocolatey.org/install
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Software
choco install adobereader -y
choco install brave -y
choco install curl -y
choco install docker-desktop -y
choco install eclipse -y
choco install git -y
choco install gitlab-runner -y
choco install intellijidea-ultimate -y
choco install maven -y
choco install nsis -y
choco install oh-my-posh -y
choco install openjdk -y
choco install powershell-core -y
choco install vim -y
choco install windirstat -y # check disk space
choco install winscp -y # easy file transfer to a linux server

# oh-my-posh font install meslo
# wsl --install
