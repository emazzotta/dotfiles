#!/bin/bash
### CORE ###
alias g='source repo'
alias gst='git status'
alias gd='git diff'
alias gcl='git clone'
alias gco='git checkout'
alias gbr='git checkout -b'
alias gadd='git add --all'
alias grm='git rm'
alias grmc='git rm --cached'
alias gtag='git tag'
alias gcontrib='git shortlog -sn --all --no-merges'
alias gce='git commit --allow-empty && git push'
alias ginit='git init && git commit -m "Initial commit" --allow-empty'
alias gitgimmeprevious='git checkout HEAD~1'
alias gup='git pull --rebase --autostash'

### BRANCHES ###
alias gbrrmlocal='git branch -D'
alias gbrrmremote='git push origin --delete'

### STASH ###
alias gstash='git stash'
alias gstashp='git stash push'
alias gapply='git stash apply'
alias gpop='git stash pop'
alias gdrop='git stash drop'
alias glist='git stash list'

### REBASE ###
alias grba='git rebase --abort'
alias grbc='git rebase --continue'
alias grbm='git rebase origin/master'
alias grbpm='git pull --rebase -s recursive -X theirs'
alias grbs='git rebase --skip'

### RESET / CLEAN ###
alias greset='git clean -f -d && git reset --hard'
alias grevert='git reset --hard'
alias rmnogit='git clean -dfx'

### TRACKING ###
alias gitnope='git update-index --assume-unchanged'
alias gityep='git update-index --no-assume-unchanged'

### SUBMODULES ###
alias gsubinitgup='git submodule init;git submodule update --init --recursive --remote --rebase'

### ARCHIVE ###
alias garchive='tar cvzf .git.tar.gz .git && rm -rf .git'
alias gunarchive='tar xvzf .git.tar.gz && rm -rf .git.tar.gz'

### SVN BRIDGE ###
alias gpsvn='git svn dcommit'
alias gupsvn='git svn fetch && git svn rebase'
alias srevert='svn revert -R .'

### EDIT GIT CONFIGS ###
alias gci='vi .gitlab-ci.yml'
alias gconf='vi $HOME/.gitconfig'
alias ggi='vi $HOME/.global_gitignore'
alias gign='vi .gitignore'
alias gsi='vi $HOME/.subversion/config'

### TUI ###
alias lig='lazygit'
alias t='lazygit'

### GITLAB ###
alias find-gitlab-pages='find . -name ".git" -type d -exec bash -c '\''repo=$(dirname "{}"); [ -d "$repo/ops/gitlab-pages"  ] && echo "✓ $repo"'\'' \;'
