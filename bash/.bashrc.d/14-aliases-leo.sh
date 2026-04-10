#!/bin/bash
### LEONARDO RUN / VPN ###
alias leo='leonardo_start'
alias leod='leonardo_start --disconnect'
alias leorunf='leorun --fast'
alias lv='leonardo_vpn_toggle'
alias lpath='leopath'
alias leop='cd "$HOME/.leonardo/25"; print_and_copy "%USERPROFILE%/.leonardo/25/LEONARDO_25.props"'

### DEPLOY ###
alias ldeploy='av && python3 src/orchestration/installer.py all --git-diff'
alias refresh_homepage='kubectl rollout restart deployment -n personal-homepage personal-homepage-server-deployment'

### FTP ###
alias leoftp='source envify LEO_FTP_USER LEO_FTP_PASS LEO_FTP_URL && lftp -e "open ftp://${LEO_FTP_USER}:${LEO_FTP_PASS}@${LEO_FTP_URL}"'
alias leoftp_mount='source envify LEO_FTP_USER LEO_FTP_PASS LEO_FTP_URL && open ftp://${LEO_FTP_USER}:${LEO_FTP_PASS}@${LEO_FTP_URL}'

### AWS / ECR ###
alias ecr_login_staging='aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 708505386411.dkr.ecr.eu-west-1.amazonaws.com'

### HASP ###
alias haspreboot='sudo launchctl unload /Library/LaunchDaemons/com.aladdin.hasplmd.plist && sudo launchctl load /Library/LaunchDaemons/com.aladdin.hasplmd.plist'
