#!/bin/bash
export WDIR="${HOME}/Projects"
export DOTFILESPATH="${WDIR}/private/dotfiles"
export CUSTOM_BIN_DIR="${DOTFILESPATH}/bin"
export PATH="${CUSTOM_BIN_DIR}:${HOME}/.yarn/bin:/usr/local/bin:/usr/local/Cellar:${PATH}"
export GDRIVEDIR="${HOME}/Google Drive"
export DOCUMENTDIR="${GDRIVEDIR}/Dokumente"
export BELEGEDIR="${DOCUMENTDIR}/Belege"
### EXPORTS ###
export APPDIR="${ROOT}/Applications"
export BOILERPLATE_PATH="${WDIR}/private/katas/boilerplate"
export CLICOLOR=1
export CRONTAB_FILE="${DOTFILESPATH}/cron/crontab"
export DESKDIR="${HOME}/Desktop"
export DOCKERDATADIR="${HOME}/Library/Containers/com.docker.docker/Data/com.docker.driver.amd64-linux"
export DOWNLOADDIR="${HOME}/Downloads"
export EDITOR=/usr/local/bin/vim
export GITDUMMYDIR="${WDIR}/private/gitdummy"
export GOPATH="${WDIR}/go-projects"
export HISTCONTROL="ignoreboth"
export HISTTIMEFORMAT="%Y-%m-%d %T "
export HOMEBREW_CASK_OPTS="--appdir=/Applications"
export KATADIR=${WDIR}/private/katas
export KEYTIMEOUT=1
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
export LC_TYPE=en_US.UTF-8
export LESSOPEN="| /usr/local/bin/src-hilite-lesspipe.sh %s"
export LSCOLORS=GxFxBxDxCxegedabagacad
export LS_COLORS="di=1;36;40:ln=1;35;40:so=1;31;40:pi=1;33;40:ex=1;32;40:bd=34;46:cd=34;43:su=0;41:sg=0;46:tw=0;42:ow=0;43:"
export MANPAGER="less -X"
export MARKDOWNDIR=${DOCUMENTDIR}/Markdown
export NODE_REPL_HISTORY="~/.node_history"
export NODE_REPL_HISTORY_SIZE='32768'
export NODE_REPL_MODE='sloppy'
export NO_COLOR='\033[0m'
export PRIVATECOMMITSDIR="${WDIR}/private/private-commits"
export PROMPT_DIRTRIM=2
export PYTHONIOENCODING='UTF-8'
export RECOMMENDED_READINGS="${MARKDOWNDIR}/recommended_readings.md"
export SDKMAN_DIR="${HOME}/.sdkman"
export TERM="xterm-256color"
export UTIL_HOST=util.mazzotta.me
export VISUAL=/usr/local/bin/vim
export WORKDIR="${DOCUMENTDIR}/Work"
export XTERM="xterm-256color"
export ZHAWDIR="${DOCUMENTDIR}/School/ZHAW"
### ALIASES ###
alias .1='cd ..'
alias .2='.1;.1'
alias .3='.2;.1'
alias .4='.3;.1'
alias .5='.4;.1'
alias .f='cd ${DOTFILESPATH}'
alias .s='cd ${HOME}/.ssh'
alias .sshrc='vi ${HOME}/.sshrc'
alias .v='cd ${HOME}/.venv'
alias .vd='cd ${HOME}/.vim_runtime'
alias .z='cd ${HOME}/.zprezto'
alias ac='cd ${DOTFILESPATH}/autocomplete'
alias aco='vi "${DOTFILESPATH}/autocomplete/custom_autocomplete"'
alias ad='cd ${WDIR}/adcubum'
alias ado='cd ${WDIR}/adcubum/gesus-offer;j10'
alias ap='cd ${WDIR}/3ap'
alias apps='cd ${APPDIR}'
alias autoc='find . \( -iname \*.h -o -iname \*.c -o -iname \*.cpp \) | xargs clang-format -style=file -i'
alias autopep='find . -name "*py" | xargs -I {} autopep8 -i {}'
alias autostart='cd ${HOME}/Library/LaunchAgents'
alias av='source "${HOME}/.venv/generic-3.7/bin/activate"'
alias bb='cd ${WDIR}/baubox/'
alias bbw='cd ${WDIR}/baubox/baubox-webapp'
alias bf='vi ${DOTFILESPATH}/Brewfile'
alias boi='cd ${BOILERPLATE_PATH}'
alias boz='cd ${WDIR}/private/bozzilli;av'
alias brci='brew cask install'
alias bri='brew install'
alias bup='echo "Updating Brew";git -C "$(brew --repo)" fetch --tags;brew update;brew upgrade;brew cleanup;brew cu -afy --cleanup;brew cleanup;sdk update'
alias c='cash'
alias cb='cd ${CUSTOM_BIN_DIR}'
alias cl='crontab -l'
alias cref='print_and_copy "${COINBASE_REFERRAL}"'
alias ctop='docker run -ti -v /var/run/docker.sock:/var/run/docker.sock quay.io/vektorlab/ctop'
alias ctun='ssh -f -C -N -L  5601:es5-catalog-master-00:5601 -L 0.0.0.0:9100:es5-catalog-data-00:9200 jump.dev.siroop.work'
alias dc='docker-compose'
alias dgc='docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v /etc:/etc -e REMOVE_VOLUMES=1 spotify/docker-gc'
alias dgui='docker run -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock -v "${DOCKERDATADIR}/data:/data" portainer/portainer;echo "Open: http://localhost:9000"'
alias diff='icdiff'
alias dign='vi .dockerignore'
alias dl='cd ${DOWNLOADDIR}'
alias dload='aria2c'
alias dnscheck='dig @1.1.1.1 ns +short'
alias dok='cd ${DOCUMENTDIR}'
alias dps='docker ps'
alias dref='print_and_copy "${DIGITAL_OCEAN_REFERRAL}"'
alias dt='cd ${DESKDIR}'
alias du="ncdu --color dark -rr -x --exclude .git --exclude node_modules"
alias dv='deactivate'
alias e='exit'
alias eak='vi ${HOME}/.ssh/authorized_keys'
alias eh='vi ${HOME}/.bash_history'
alias ekh='vi ${HOME}/.ssh/known_hosts'
alias ema='cd ${WDIR}/private/emanuele-page;av'
alias emptytrash='sudo rm -rfv /Volumes/*/.Trashes; sudo rm -rfv ~/.Trash; sudo rm -rfv /private/var/log/asl/*.asl; sqlite3 ~/Library/Preferences/com.apple.LaunchServices.QuarantineEventsV* "delete from LSQuarantineEvent"'
alias ep='vi ${HOME}/.bashrc;rp'
alias er='vi README.md'
alias err='vi ${RECOMMENDED_READINGS}'
alias etm='vi ${HOME}/.tmux.conf.local'
alias ev='vi .env'
alias finddup='find . -type f -name '\''*(1)*'\'' | xargs -I {} echo {} | sed '\''s/ /\\ /g'\'' | xargs -I {} bash -c '\''cd "{}";echo "{}"'\'''
alias flush='dscacheutil -flushcache && killall -HUP mDNSResponder'
alias fonts='cd /Library/Fonts'
alias g='repo'
alias gadd='git add --all'
alias gapply='git stash apply'
alias garchive='tar cvzf .git.tar.gz .git && rm -rf .git'
alias gbl='git blame'
alias gbr='git checkout -b'
alias gbrrmlocal='git branch -D'
alias gbrrmremote='git push origin --delete'
alias gce='git commit --allow-empty && git push'
alias gci='vi .gitlab-ci.yml'
alias gcl='git clone'
alias gco='git checkout'
alias gconf='vi ${HOME}/.gitconfig'
alias gcontrib='git shortlog -sn --all --no-merges'
alias gd='git diff'
alias gdbbackup='docker exec gesus.mariadb /usr/bin/mysqldump --complete-insert --quick --single-transaction -u gesus -pgesus gesus > backup.sql'
alias gdl='./gradlew'
alias gdrive='cd ${GDRIVEDIR}'
alias gdrop='git stash drop'
alias genpubpem='openssl rsa -in ${HOME}/.ssh/id_rsa -pubout > ${HOME}/.ssh/id_rsa.pub.pem'
alias genvenv2='virtualenv -p python2.7'
alias genvenv3='virtualenv -p python3.7'
alias gesus-ftp='lftp sftp://${SWICA_FTP_USER}:$(security find-internet-password -wj swica)@${SWICA_FTP_URL}  -e "cd ${SWICA_FTP_PATH}; ls"'
alias ggi='vi ${HOME}/.global_gitignore'
alias gign='vi .gitignore'
alias ginit='git init && git commit -m "Initial commit" --allow-empty'
alias gitnope='git update-index --assume-unchanged'
alias gityep='git update-index --no-assume-unchanged'
alias glist='git stash list'
alias glog='git log'
alias glogp='git log --pretty=format:'\''%h by %an:%n"%s"'\'' --graph'
alias gpgd='gpg --decrypt'
alias gpgpub='print_and_copy "$(gpg --armor --export mazzotta.emanuele@gmail.com)"'
alias gpgsearch='gpg --keyserver pool.sks-keyservers.net --search-keys'
alias gpgsend='gpg --keyserver hkp://ipv4.pool.sks-keyservers.net:80 --send-keys 8A7772B5326021E6845D291F73EB5C8CAC4297A8'
alias gpop='git stash pop'
alias gr='while [[ ! -e ".git" && "$(pwd)" !=  "/" ]]; do;cd ..;done'
alias grba='git rebase --abort'
alias grbc='git rebase --continue'
alias grbm='git rebase origin/master'
alias grbpm='git pull --rebase -s recursive -X theirs'
alias grbs='git rebase --skip'
alias grep='grep -i --color=auto'
alias greset='git clean -f -d && git reset --hard'
alias grevert='git reset --hard'
alias grm='git rm'
alias grmc='git rm --cached'
alias gsinit='git submodule init'
alias gsreset='git submodule update --init'
alias gst='git status'
alias gstash='git stash'
alias gstashkp='git stash --keep-index'
alias gstashs='git stash -p'
alias gsup='git submodule init;git submodule update --rebase --remote'
alias gtag='git tag'
alias gunarchive='tar xvzf .git.tar.gz && rm -rf .git.tar.gz'
alias gunco='git reset --soft HEAD~1'
alias gup='git pull --rebase'
alias h='cd ${HOME}'
alias harvest='(cd ${WDIR}/private/timetracker && dc run --rm timetracker)'
alias hollywood='docker run -ti jess/hollywood'
alias hp='cd ${WDIR}/private/homepage;av'
alias hrp='cd ${WDIR}/hackathons'
alias hz='cd ${WDIR}/hackathons/sustineri'
alias inf='cd ${WDIR}/private/infrastructure'
alias infu='inf && ./update'
alias irp='cd ${WDIR}/interviews'
alias isotoutf='iconv -f iso-8859-1 -t utf-8'
alias j10="sdk use java 10.0.2-open"
alias j11="sdk use java 11.0.0-open"
alias j12="sdk use java 12.ea.15-open"
alias j8="sdk use java 8.0.191-oracle"
alias j9="sdk use java 9.0.4-open"
alias k='kubectl'
alias ke='vi ${HOME}/.config/karabiner/karabiner.json'
alias killgpg='killall ssh-agent gpg-agent;gpgconf --kill all'
alias ks='killall ssh'
alias kt='cd ${KATADIR}'
alias l='clear'
alias lb='cd ${WDIR}/private/lighthouse-badges'
alias ll='ls -ltra'
alias localdbs='mysql -h 127.0.0.1 -u root <<< "SHOW DATABASES;"'
alias lrr='print_and_copy ${BOOKLIST_LINK}'
alias m='make'
alias mailplugins='cd /Library/Mail/Bundles/'
alias mc='make clean'
alias me='vi Makefile'
alias ml='make lint'
alias ms='make start'
alias mt='make test'
alias mysqlrun='docker run -p 0.0.0.0:3306:3306 -e MYSQL_USER=mysql -e MYSQL_PASSWORD=mysql -e MYSQL_DATABASE=mysql -e MYSQL_ROOT_PASSWORD=mysql -d mysql'
alias now='print_and_copy $(date "+%Y-%m-%d-%H-%M-%S")'
alias nref='print_and_copy "${NURA_REFERRAL}"' # Nuraphones
alias oref='print_and_copy "${OURA_REFERRAL}"' # Oura Ring
alias path='echo -e ${PATH//:/\\n}'
alias ph='cd ${WDIR}/private/plexius-homepage'
alias ping='prettyping --nolegend'
alias pipinstall='curl https://bootstrap.pypa.io/get-pip.py | python'
alias pipup='pip install --upgrade pip'
alias postgresrun='docker run -p 0.0.0.0:5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres -d postgres'
alias prp='cd ${WDIR}/private'
alias py='av;ptpython3;dv'
alias record='asciinema rec'
alias repo='source ${CUSTOM_BIN_DIR}/repo'
alias rma='rmds;rmwin;rmpy;rmlog'
alias rmds="find . -type f -name '.DS_Store*' -delete"
alias rmlog="find . -type f -name '*.log' -delete"
alias rmnogit='git clean -dfx'
alias rmpy="find . -type f -name '*.pyc' -o -name '.cache' -o -name 'target' -o -name '.coverage' -o -name '__pycache__' -delete"
alias rmu='git clean -f' # Remove untracked files
alias rmwin="find . -type f -name 'Thumbs.db' -or -name 'desktop.ini' -or -name '$RECYCLE.BIN' -delete"
alias rmzero='find . -size 0 | xargs rm'
alias rp='source ${HOME}/.bashrc'
alias rr='rm -rf'
alias rref='print_and_copy "${REFIND_REFERRAL}"'
alias sconf='vi ${HOME}/.ssh/config'
alias see="fzf --preview 'less {}'"
alias shrug='print_and_copy "¯\_(ツ)_/¯"'
alias sig='cd "${HOME}/Library/Mobile Documents/com~apple~mail/Data/V4/Signatures"'
alias smref='print_and_copy "${SMIDE_REFERRAL}"' # Smide
alias sounds='cd /System/Library/Sounds'
alias spub='print_and_copy "$(ls ${HOME}/.ssh/id_*.pub | xargs -I {} sh -c "cat {} && echo")"'
alias sq='cd ${WDIR}/squido/squidoapi'
alias sqa='cd ${WDIR}/squido/squidoandroid'
alias sqi='cd ${WDIR}/squido/squidoios'
alias sqr='cd ${WDIR}/squido/squidoreact'
alias sqref='print_and_copy "${SWISSQUOTE_REFERRAL}"'
alias sqw='cd ${WDIR}/squido/squidoweb'
alias sref='print_and_copy "${SELMA_REFERRAL}"'
alias srp='cd ${WDIR}/archive/siroop'
alias ss='sshrc'
alias st='vi ${DOTFILESPATH}/setup'
alias superocd='(infu) && ocd && update && gupallin "${HOME}" && zgen update <<< "n" &> /dev/null && gck'
alias t='tig'
alias thinking='print_and_copy 🤔'
alias tick='print_and_copy "✓"'
alias timer='echo "Timer started. Stop with Ctrl-D." && date && time cat && date'
alias tm='tmux'
alias tma='tmux attach -t'
alias tmk='tmux kill-session -t'
alias tml='tmux ls'
alias trp='cd ${WDIR}/tools'
alias tz='date "+%z %Z"'
alias unow='print_and_copy $(date +%s)'
alias update='softwareupdate -i -a; bup; npm install npm -g; npm update -g; gem update --system; gem update; gem cleanup'
alias uref='print_and_copy "${UBER_REFERRAL}"' # Uber
alias urlencode='python -c "import sys, urllib; print urllib.quote_plus(sys.argv[1]);"'
alias urr='gist -u ${RECOMMENDED_READINGS_GIST_ID} ${RECOMMENDED_READINGS}'
alias vdc='vi docker-compose.yml'
alias vdf='vi Dockerfile'
alias ve='vi ${HOME}/.vim_runtime/my_configs.vim'
alias vh='sudo vi /etc/hosts'
alias vi='vim'
alias vmconnect='sshrc -XY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 user@127.0.0.1'
alias vmup='VBoxManage startvm "Ubuntu" --type headless'
alias w='cd ${WDIR}'
alias webgoat='docker run -p 8080:8080 -t webgoat/webgoat-7.1'
alias wrk='cd ${WORKDIR}'
alias y='yarn'
alias ya='yarn add'
alias yl='yarn lint:fix'
alias yr='yarn remove'
alias ys='yarn start'
alias yt='yarn test'
alias z='. ${CUSTOM_BIN_DIR}/z'
alias ze='vi ${HOME}/.zshrc'
alias zep='vi ${HOME}/.zpreztorc'
alias zh='vi ${HISTFILE}'
alias zhaw='cd ${ZHAWDIR}/Classes'
alias zhawconnect='sudo openconnect ras.zhaw.ch <<< $(echo "mazzoema\n`security find-generic-password -wa mazzoema`")'
alias zm='cd ${WDIR}/zhaw/zhaw-material'
alias zrp='cd ${WDIR}/zhaw'
### COMMANDS ###
source load "${DOTFILESPATH}/.env"
source load "${DOTFILESPATH}/bin/colors"
source load "${DOTFILESPATH}/autocomplete/custom_autocomplete"
source load "${HOME}/.sdkman/bin/sdkman-init.sh"
test "${BASH_VERSION}" && source load "${HOME}/.sshrc"
if test "${ZSH_VERSION}"; then
    source "${HOME}/.zgen/zgen.zsh"
    if ! zgen saved; then
        zgen prezto
        zgen prezto git
        zgen prezto history-substring-search
        zgen prezto syntax-highlighting
        zgen load ${DOTFILESPATH}/autocomplete/zsh 
        zgen load djui/alias-tips
        zgen load junegunn/fzf shell
        zgen load zsh-users/zsh-syntax-highlighting
        zgen load tarruda/zsh-autosuggestions
        zgen save
    fi
fi
if test -f ${HOME}/.gnupg/.gpg-agent-info -a -n "$(pgrep gpg-agent)"; then
    source ${HOME}/.gnupg/.gpg-agent-info
else
    eval $(gpg-agent --daemon --write-env-file ${HOME}/.gnupg/.gpg-agent-info)
fi
