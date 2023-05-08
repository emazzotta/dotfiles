#!/bin/bash
### MAIN EXPORTS ###
export WDIR="$HOME/Projects"
export DOTFILESPATH="$WDIR/private/dotfiles"
export CUSTOM_BIN_DIR="$DOTFILESPATH/bin"
export ANDROID_AVD_HOME=$HOME/.android/avd
export ANDROID_HOME=$HOME/Library/Android/sdk
export ANDROID_SDK=$HOME/Library/Android/sdk
export ANDROID_SDK_ROOT=$HOME/Library/Android/sdk
export GDRIVEDIR="$HOME/Google_Drive"
export DOCUMENTDIR="$GDRIVEDIR/Dokumente"
### PATH EXPORTS ###
export PATH="$CUSTOM_BIN_DIR:$PATH"
export PATH="$HOME/.cargo/bin:$PATH"
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.docker/bin:$PATH"
export PATH="$PATH:$ANDROID_HOME/emulator"
export PATH="$PATH:$ANDROID_HOME/platform-tools"
export PATH="$PATH:$ANDROID_HOME/tools"
export PATH="$PATH:$ANDROID_HOME/tools/bin"
export PATH="$PATH:$HOME/.bun/bin"
export PATH="/opt/homebrew/opt/openssl@3/bin:$PATH"
export PATH="/opt/homebrew/bin:$PATH"
export PATH="$HOME/.yarn/bin:$HOME/.config/yarn/global/node_modules/.bin:$PATH"
### EXPORTS ###
export APPDIR="$ROOT/Applications"
export BOILERPLATE_PATH="$WDIR/private/katas/boilerplate"
export BOOKMARKDIR=$DOCUMENTDIR/Bookmarks
export CLICOLOR=1
export CRONTAB_FILE="$DOTFILESPATH/cron/crontab"
export DESKDIR="$HOME/Desktop"
export DOWNLOADDIR="$HOME/Downloads"
export EDITOR=/opt/homebrew/bin/vim
export GITDUMMYDIR="$WDIR/private/gitdummy"
export GLOBAL_ENV_FILE="$DOTFILESPATH/.env"
export HISTCONTROL="ignoreboth"
export HISTTIMEFORMAT="%Y-%m-%d %T "
export HOMEBREW_CASK_OPTS="--appdir=/Applications"
export IDEA_VM_OPTIONS="$HOME/Library/Application Support/JetBrains/IntelliJIdea2022.3/idea.vmoptions"
export JAVA_HOME="$HOME/.sdkman/candidates/java/current"
export KEYTIMEOUT=1
export KUBE_DIR="$HOME/.kube"
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
export LC_TYPE=en_US.UTF-8
export LESS='-R'
export LSCOLORS="GxFxBxDxCxegedabagacad"
export LS_COLORS="di=1;36;40:ln=1;35;40:so=1;31;40:pi=1;33;40:ex=1;32;40:bd=34;46:cd=34;43:su=0;41:sg=0;46:tw=0;42:ow=0;43:"
export MANPAGER="less -X"
export MARKDOWNDIR=$DOCUMENTDIR/Markdown
export NODE_REPL_HISTORY="~/.node_history"
export NODE_REPL_HISTORY_SIZE='32768'
export NODE_REPL_MODE='sloppy'
export PRIVATECOMMITSDIR="$WDIR/private/private-commits"
export PROMPT_DIRTRIM=2
export PYTHONIOENCODING='UTF-8'
export RECOMMENDED_READINGS="$MARKDOWNDIR/recommended_readings.md"
export SDKMAN_DIR="$HOME/.sdkman"
export TERM="xterm-256color"
export VENV_PATH="$HOME/.venv"
export VENV_PYTHON_3="$VENV_PATH/python-3-venv"
export VIM_RUNTIME_DIR="$HOME/.vim_runtime"
export VISUAL="$EDITOR"
export XTERM="xterm-256color"
export ZHAWDIR="$DOCUMENTDIR/School/ZHAW"
### ALIASES ###
alias .1='cd ..'
alias .2='.1;.1'
alias .3='.2;.1'
alias .4='.3;.1'
alias .5='.4;.1'
alias .a='cd $DOTFILESPATH/autocomplete'
alias .du='du -hsx * | sort -rh | head -10'
alias .f='cd $DOTFILESPATH'
alias .k='cd $KUBE_DIR'
alias .s='cd $HOME/.ssh'
alias .sshrc='vi $HOME/.sshrc'
alias .sshrcd='cd $HOME/.sshrc.d'
alias .v='cd $VENV_PATH'
alias aco='vi "$DOTFILESPATH/autocomplete/custom_autocomplete"'
alias androidup='emulator -avd Pixel_C_API_30 &'
alias ap='cd $WDIR/3ap'
alias apps='cd $APPDIR'
alias asciitoutf='iconv -f US-ASCII -t utf-8'
alias autoc='find . -iname *.h -o -iname *.c -o -iname *.cpp | xargs clang-format -style=file -i'
alias autopep='av;find . -name "*py" | xargs -I {} autopep8 -i {};dv'
alias autostart='cd $HOME/Library/LaunchAgents'
alias av='source "$VENV_PYTHON_3/bin/activate"'
alias bf='vi $DOTFILESPATH/Brewfile'
alias bfdump='brew bundle dump'
alias boi='cd $BOILERPLATE_PATH'
alias bom='echo -ne "\xEF\xBB\xBF"'
alias brew='arch -arm64 brew'
alias bri='brew install'
alias bru='brew uninstall'
alias bup='echo "Updating Brew";git -C "$(brew --repo)" fetch --tags;brew update;brew upgrade;brew upgrade --cask --greedy;brew cleanup;brew cu -afy --cleanup;brew cleanup;rm_brew_pkg'
alias cb='cd $CUSTOM_BIN_DIR'
alias cl='crontab -l'
alias cpwd='print_and_copy $(pwd)'
alias create_backups='envify && tmbackup && bookmarks_backup && notion_backup'
alias ctop='docker run -ti -v /var/run/docker.sock:/var/run/docker.sock quay.io/vektorlab/ctop'
alias dc='docker-compose'
alias dgui='docker run --rm -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock portainer/portainer;echo "Open: http://localhost:9000"'
alias diff='icdiff'
alias dign='vi .dockerignore'
alias dj='cd $DJ_TRACKS'
alias dl='cd $DOWNLOADDIR'
alias dload='aria2c'
alias dnscheck='dig @1.1.1.1 ns +short'
alias docker_prune='docker system prune -a -f --volumes'
alias dok='cd $DOCUMENTDIR'
alias dps='docker ps'
alias dr='cd $GDRIVEDIR'
alias dt='cd $DESKDIR'
alias dv='deactivate'
alias e='exit'
alias eak='vi $HOME/.ssh/authorized_keys'
alias ecr_login_staging='aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 708505386411.dkr.ecr.eu-west-1.amazonaws.com'
alias eh='vi $HOME/.bash_history'
alias ekh='vi $HOME/.ssh/known_hosts'
alias ema='cd $WDIR/private/emanuele-page;av'
alias envify='source "$GLOBAL_ENV_FILE"'
alias ep='vi $HOME/.bashrc;rp'
alias er='vi README.md'
alias err='vi $RECOMMENDED_READINGS'
alias etm='vi $HOME/.tmux.conf.local'
alias etmg='vi $HOME/.tmux.conf'
alias ev='vi .env'
alias evscode="vi ${DOTFILESPATH}/vscode/settings.json"
alias eyes='print_and_copy "( ͡° ͜ʖ ͡°) ( ͡⊙ ͜ʖ ͡⊙) ( ͡◉ ͜ʖ ͡◉)"'
alias find_duplicate='find . -type f -maxdepth 4 -exec basename {} \; | sort -rn |  uniq -d'
alias g='source repo'
alias gadd='git add --all'
alias gapply='git stash apply'
alias garchive='tar cvzf .git.tar.gz .git && rm -rf .git'
alias gbr='git checkout -b'
alias gbrrmlocal='git branch -D'
alias gbrrmremote='git push origin --delete'
alias gce='git commit --allow-empty && git push'
alias gcl='git clone'
alias gco='git checkout'
alias gconf='vi $HOME/.gitconfig'
alias gcontrib='git shortlog -sn --all --no-merges'
alias gd='git diff'
alias gdrop='git stash drop'
alias genvenv3='virtualenv -p python3.10'
alias ggi='vi $HOME/.global_gitignore'
alias gign='vi .gitignore'
alias ginit='git init && git commit -m "Initial commit" --allow-empty'
alias gitgimmeprevious='git checkout HEAD~1'
alias gitnope='git update-index --assume-unchanged'
alias gityep='git update-index --no-assume-unchanged'
alias glist='git stash list'
alias gpop='git stash pop'
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
alias gstashp='git stash push'
alias gsubmodule='git submodule init;git submodule update --rebase --remote'
alias gtag='git tag'
alias gunarchive='tar xvzf .git.tar.gz && rm -rf .git.tar.gz'
alias gup='git pull --rebase --autostash'
alias hp='cd $WDIR/private/homepage;av'
alias hrp='cd $WDIR/hackathons'
alias inf='cd $WDIR/private/infrastructure'
alias irp='cd $WDIR/interviews'
alias isotoutf='iconv -f iso-8859-1 -t utf-8'
alias j11='sdk use java $(find_java_sdk 11)'
alias j17='sdk use java $(find_java_sdk 17)'
alias j8='sdk use java $(find_java_sdk 8)'
alias jc='find . -name "build" -or -name "out" -or -name "generated" | xargs -I {} rm -rf {}'
alias k='kubectl'
alias kc='kubeconf'
alias ke='vi $HOME/.config/karabiner/karabiner.json'
alias killgpg='killall ssh-agent gpg-agent;gpgconf --kill all'
alias kn='kubens'
alias l='clear'
alias lb='cd $WDIR/private/lighthouse-badges'
alias lig='lazygit'
alias ll='ls -lah'
alias localdbs='mysql -h 127.0.0.1 -u root <<< "SHOW DATABASES;"'
alias lrr='print_and_copy $BOOKLIST_LINK'
alias ls='lsd'
alias m='make'
alias macsoftwareupdate='softwareupdate -i -a'
alias me='vi Makefile'
alias mkf='cd $WDIR/mikafi'
alias mkfkill='yes | killprocess "Projects/mikafi"'
alias mpc='envify && yes "$PASSWORD_ZIPS" | 7z x "$ZIPS_DIR/MPC.7z" -o"$DESKDIR"'
alias node_modules_size='find . -name "node_modules" -type d -prune | xargs du -chs'
alias now='print_and_copy $(date "+%Y-%m-%d-%H-%M-%S")'
alias pbp='pwd | pbcopy'
alias ph='cd $WDIR/private/plexius-homepage'
alias ping='prettyping --nolegend'
alias postgresrun='docker run -p 0.0.0.0:5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres -d postgres'
alias prp='cd $WDIR/private'
alias pwz='envify && echo -ne "$PASSWORD_ZIPS" | pbcopy'
alias py='av;ptpython;dv'
alias record='asciinema rec'
alias reinstall_py='rm -rf "$VENV_PYTHON_3";pip install virtualenv && genvenv3 "$VENV_PYTHON_3" && av && pip install --upgrade pip && pip install -r $DOTFILESPATH/python/requirements.txt && ycminstall'
alias rekordboxxml='vi $GDRIVEDIR/Music/DJing/Rekordbox/rekordbox.xml'
alias rm_act_cache='rm -rf $HOME/.cache/act'
alias rm_brew_pkg='find "/opt/homebrew/Caskroom" -type f -name "*.pkg" -delete && rm -rf "$HOME/Library/Caches/Homebrew/downloads" && mkdir -p "$HOME/Library/Caches/Homebrew/downloads"'
alias rm_microsoft_autoupdater='sudo rm -rf "/Library/Application Support/Microsoft/MAU2.0"'
alias rm_node_modules='find "$(pwd)" -type d -name "node_modules" -exec rm -rf {} \;'
alias rmds="find . -type f -name '.DS_Store*' -delete"
alias rmjsdk='rm -rf "$HOME/.sdkman/archives/";mkdir -p "$HOME/.sdkman/archives/"'
alias rmlog="find . -type f -name '*.log' -delete"
alias rmnogit='git clean -dfx'
alias rmpy="find . -type f -name '*.pyc' -o -name '.cache' -o -name 'target' -o -name '.coverage' -o -name '__pycache__' -delete"
alias rmraycastclipboard='rm -rf "$HOME/Library/Caches/com.raycast.macos/Clipboard" && mkdir -p "$HOME/Library/Caches/com.raycast.macos/Clipboard"'
alias rmwin="find . -type f -name 'Thumbs.db' -or -name 'desktop.ini' -or -name '$RECYCLE.BIN' -delete"
alias rmzero='find . -size 0 | xargs rm'
alias rnup='$HOME/Projects/mikafi/roasterapp/node_modules/react-native/scripts/launchPackager.command'
alias rp='source $HOME/.bashrc'
alias rr='rm -rf'
alias sconf='vi $HOME/.ssh/config'
alias sdkmanupdate='yes | sdk update;rmjsdk'
alias see="fzf --preview 'less {}'"
alias serials='envify && cd "$SERIALSDIR"'
alias shrug='print_and_copy "¯\_(ツ)_/¯"'
alias spacey='envify && yes "$PASSWORD_ZIPS" | 7z x "$ZIPS_DIR/Spacey.7z" -o"$DESKDIR"'
alias spotify_clean='rm -rf /Users/$USERNAME/Library/Caches/com.spotify.client/Data'
alias spub='find $HOME/.ssh -name "id_*.pub" | while read file;do echo "$file:" && cat $file;done'
alias srp='cd $WDIR/archive/siroop'
alias ss='sshrc'
alias sshpasswd='ssh-keygen -p -f'
alias st='vi $DOTFILESPATH/setup'
alias superocd='ocd && update && rmraycastclipboard && rm_act_cache && gupallin "$HOME" && zgen update <<< "n" &> /dev/null && gck "$HOME" && create_backups'
alias t='lazygit'
alias tags_fixer='envify && av && tags_fixer.py'
alias thinking='print_and_copy 🤔'
alias tick='print_and_copy "✓"'
alias timer='echo "Timer started. Stop with Ctrl-D." && date && time cat && date'
alias tm='tmux'
alias tma='tmux attach -t'
alias tmk='tmux kill-session -t'
alias tml='tmux ls'
alias tracks='envify && tracks_stats'
alias trp='cd $WDIR/tools'
alias tz='date "+%z %Z"'
alias unow='print_and_copy $(date +%s)'
alias update='macsoftwareupdate;bup;npm install -g npm;sdkmanupdate;vimpluginupdate;python -m pip install --upgrade pip'
alias upsidedown='print_and_copy 🙃'
alias utmdir='cd $HOME/Library/Containers/com.utmapp.UTM/Data/Documents'
alias vd='cd $VIM_RUNTIME_DIR'
alias vdc='vi docker-compose.yml'
alias vdf='vi Dockerfile'
alias ve='vi $VIM_RUNTIME_DIR/my_configs.vim'
alias vh='sudo vi /etc/hosts'
alias vi='vim'
alias vskill='yes | killprocess "vsls-agent";yes | killprocess "Code Helper (Renderer)"'
alias w='cd $WDIR'
alias wscat='npx wscat'
alias y='yarn'
alias yarnupdate='curl --compressed -o- -L https://yarnpkg.com/install.sh | bash'
alias ze='vi $HOME/.zshrc'
alias zep='vi $HOME/.zpreztorc'
alias zh='vi $HISTFILE'
alias zrp='cd $WDIR/zhaw'
### COMMANDS ###
source load "$HOME/.sdkman/bin/sdkman-init.sh"
source load "$DOTFILESPATH/autocomplete/custom_autocomplete"
source load "$DOTFILESPATH/bin/colors"
test "$BASH_VERSION" && source load "$HOME/.sshrc"
if test "$ZSH_VERSION"; then
    source "$HOME/.zgen/zgen.zsh"
    source load "$DOTFILESPATH/bin/zshaddhistory"
    source load "$DOTFILESPATH/autocomplete/zsh/_kubectl"
    source load "$DOTFILESPATH/autocomplete/zsh/_bun"
    # If a new one is added, just zgen reset
    if ! zgen saved; then
        zgen prezto
        zgen prezto git
        zgen prezto history-substring-search
        zgen prezto syntax-highlighting
        zgen load $DOTFILESPATH/autocomplete/zsh 
        zgen load junegunn/fzf shell
        zgen load zsh-users/zsh-syntax-highlighting
        zgen load tarruda/zsh-autosuggestions
        zgen save
        compinit
    fi
fi
### NVM ###
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"  # This loads nvm
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"  # This loads nvm bash_completion

