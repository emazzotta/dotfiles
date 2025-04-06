#!/bin/bash

### MAIN EXPORTS ###
export ANDROID_AVD_HOME=$HOME/.android/avd
export ANDROID_HOME=$HOME/Library/Android/sdk
export ANDROID_SDK=$HOME/Library/Android/sdk
export ANDROID_SDK_ROOT=$HOME/Library/Android/sdk

export WDIR="$HOME/Projects"
export PRIVATE_PROJECTS="$WDIR/private"
export DOTFILESPATH="$PRIVATE_PROJECTS/dotfiles"
export CUSTOM_BIN_DIR="$DOTFILESPATH/bin"

export GDRIVEDIR="/Volumes/SanDisk_1TB/Backup/Google_Drive"
export DOCUMENTDIR="$GDRIVEDIR/Dokumente"

export DJ_DIR="$HOME/Music/01_DJ"
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
export BOILERPLATE_PATH="$PRIVATE_PROJECTS/katas/boilerplate"
export BOOKMARKDIR=$DOCUMENTDIR/Bookmarks
export BREW_CASK_IGNORELIST="mixed-in-key,my-cask-to-pin"
export BREW_CASK_IGNORELIST=$(echo $BREW_CASK_IGNORELIST | sed 's/,/\\|/g')
export CC="/opt/homebrew/bin/gcc-14"
export CLICOLOR=1
export CMAKE_CXX_COMPILER="/opt/homebrew/bin/g++-14"
export CMAKE_CXX_FLAGS="-std=c++17"
export CMAKE_CXX_STANDARD="17"
export CMAKE_C_COMPILER="/opt/homebrew/bin/gcc-14"
export CMAKE_EXE_LINKER_FLAGS="-lstdc++fs"
export CMAKE_MAKE_PROGRAM=$(which ninja)
export CMAKE_OPTIONS="-DUSE_SYSTEM_LIBCLANG=ON"
export CRONTAB_FILE="$DOTFILESPATH/cron/crontab"
export CXX="/opt/homebrew/bin/g++-14"
export DESKDIR="$HOME/Desktop"
export DJ_TRACKS="$DJ_DIR/00_Collection"
export DOWNLOADDIR="$HOME/Downloads"
export EDITOR=/opt/homebrew/bin/vim
export GITDUMMYDIR="$PRIVATE_PROJECTS/gitdummy"
export GLOBAL_ENV_FILE="$DOTFILESPATH/.env"
export HISTCONTROL="ignoreboth"
export HISTTIMEFORMAT="%Y-%m-%d %T "
export HOMEBREW_CASK_OPTS="--appdir=/Applications"
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
export POSH_THEMES_PATH="$(brew --prefix oh-my-posh)/themes"
export PRIVATECOMMITSDIR="$PRIVATE_PROJECTS/private-commits"
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
alias ae='envify'
alias af='audiofix'
alias afa='audiofixall'
alias ai_gpt='av && envify && interpreter'
alias ai_llama='av && envify && interpreter --local'
alias androidup='emulator -avd Pixel_C_API_30 &'
alias ap='cd $WDIR/3ap'
alias apps='cd $APPDIR'
alias as='audiospec'
alias asa='audiospecall'
alias asciitoutf='iconv -f US-ASCII -t utf-8'
alias audiofix='envify && av && audiotags_manager --full-tag-optimizer'
alias audiofixall='envify && av && find . -type f \( -name "*.mp3" -o -name "*.wav" -o -name "*.flac" \) -exec audiotags_manager --full-tag-optimizer {} \;'
alias audiospecall='find . -type f \( -name "*.mp3" -o -name "*.wav" -o -name "*.flac" \) -exec audiospec {} \;'
alias autoc='find . -iname *.h -o -iname *.c -o -iname *.cpp | xargs clang-format -style=file -i'
alias autopep='av;find . -name "*py" | xargs -I {} autopep8 -i {};dv'
alias autostart='cd $HOME/Library/LaunchAgents'
alias av='if [ -f "./venv/bin/activate"  ]; then source "./venv/bin/activate"; else source "$VENV_PYTHON_3/bin/activate"; fi'
alias bf='vi $DOTFILESPATH/brew/Brewfile'
alias bfdump='brew bundle dump'
alias boi='cd $BOILERPLATE_PATH'
alias bom='echo -ne "\xEF\xBB\xBF"'
alias brew='arch -arm64 brew'
alias bri='brew install'
alias bru='brew uninstall'
alias bup='echo "Updating Brew";git -C "$(brew --repo)" fetch --tags;brew update;brew upgrade;brew cu pin mixed-in-key;brew cu -afy --cleanup;brew cleanup;rm_brew_pkg'
alias cb='cd $CUSTOM_BIN_DIR'
alias ce='crontab_editor'
alias cl='crontab -l'
alias cpwd='print_and_copy $(pwd)'
alias create_backups='envify && tmbackup && bookmarks_backup'
alias ctop='docker run -ti -v /var/run/docker.sock:/var/run/docker.sock quay.io/vektorlab/ctop'
alias dc='docker-compose'
alias dcp='docker-compose -f docker-compose.production.yml'
alias dgui='docker run --rm -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock portainer/portainer;echo "Open: http://localhost:9000"'
alias diff='icdiff'
alias dign='vi .dockerignore'
alias dive='docker run -ti --rm  -v /var/run/docker.sock:/var/run/docker.sock wagoodman/dive'
alias dj='cd $DJ_DIR'
alias dl='cd $DOWNLOADDIR'
alias dload='aria2c'
alias dnscheck='dig @1.1.1.1 ns +short'
alias dnsflush='sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder'
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
alias encrypt='hashify'
alias envify='source "$GLOBAL_ENV_FILE"'
alias ep='vi $HOME/.bashrc;rp'
alias er='vi README.md'
alias err='vi $RECOMMENDED_READINGS'
alias etm='vi $HOME/.tmux.conf.local'
alias etmg='vi $HOME/.tmux.conf'
alias ev='vi .env'
alias evscode="vi ${DOTFILESPATH}/vscode/settings.json"
alias eyes='print_and_copy "( ͡° ͜ʖ ͡°) ( ͡⊙ ͜ʖ ͡⊙) ( ͡◉ ͜ʖ ͡◉)"'
alias find_duplicate='find . -type f -maxdepth 4 -exec basename {} \; | sort -rn | uniq -d | while read dup; do find . -type f -maxdepth 4 -name "$dup"; done'
alias g='source repo'
alias gadd='git add --all'
alias gapply='git stash apply'
alias garchive='tar cvzf .git.tar.gz .git && rm -rf .git'
alias gbr='git checkout -b'
alias gbrrmlocal='git branch -D'
alias gbrrmremote='git push origin --delete'
alias gce='git commit --allow-empty && git push'
alias gci='vi .gitlab-ci.yml'
alias gcl='git clone'
alias gco='git checkout'
alias gconf='vi $HOME/.gitconfig'
alias gcontrib='git shortlog -sn --all --no-merges'
alias gd='git diff'
alias gdrop='git stash drop'
alias genvenv3='virtualenv -p python3.12'
alias ggi='vi $HOME/.global_gitignore'
alias gign='vi .gitignore'
alias ginit='git init && git commit -m "Initial commit" --allow-empty'
alias gitgimmeprevious='git checkout HEAD~1'
alias gitnope='git update-index --assume-unchanged'
alias gityep='git update-index --no-assume-unchanged'
alias glist='git stash list'
alias gpop='git stash pop'
alias gpsvn='git svn dcommit'
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
alias gsi='vi $HOME/.subversion/config'
alias gst='git status'
alias gstash='git stash'
alias gstashp='git stash push'
alias gsubinitgup='git submodule init;git submodule update --init --recursive --remote --rebase'
alias gtag='git tag'
alias gunarchive='tar xvzf .git.tar.gz && rm -rf .git.tar.gz'
alias gunstage='git restore --staged .'
alias gup='git pull --rebase --autostash'
alias gupsvn='git svn fetch && git svn rebase'
alias hrp='cd $WDIR/hackathons'
alias isotoutf='iconv -f iso-8859-1 -t utf-8'
alias j21intel='export JAVA_HOME=$WDIR/leo-productions/jdk-21.jdk/Contents/Home'
alias jc='find . -name "build" -or -name "out" -or -name "generated" | xargs -I {} rm -rf {}'
alias jv='java -version'
alias k='kubectl'
alias kc='kubeconf'
alias ke='vi $HOME/.config/karabiner/karabiner.json'
alias killgpg='killall ssh-agent gpg-agent;gpgconf --kill all'
alias kl='cd $HOME/Daten'
alias kn='kubens'
alias l='printf "\033[H\033[2J"'
alias lb='cd $PRIVATE_PROJECTS/lighthouse-badges'
alias leo='leonardo_start'
alias lig='lazygit'
alias ll='ls -lah'
alias localdbs='mysql -h 127.0.0.1 -u root <<< "SHOW DATABASES;"'
alias lrp='cd $WDIR/leo-productions'
alias lrr='print_and_copy $BOOKLIST_LINK'
alias ls='lsd'
alias lv='leonardo_vpn_toggle'
alias m='make'
alias macsoftwareupdate='softwareupdate -i -a'
alias me='vi Makefile'
alias mpc='envify && 7z x "$GDRIVEDIR/Dokumente/Zipped_PW/MPC.7z" -o"$DESKDIR" -p"$PASSWORD_ZIPS"'
alias node_modules_size='find . -name "node_modules" -type d -prune | xargs du -chs'
alias nopw='ssh-copy-id'
alias now='print_and_copy $(date "+%Y-%m-%d-%H-%M-%S")'
alias pbp='pwd | pbcopy'
alias ph='cd $PRIVATE_PROJECTS/plexius-homepage'
alias ping='prettyping --nolegend'
alias portal_reset='yarn && docker-compose down && docker-compose up -d database && yarn clean && yarn generate && yarn build && yarn dev'
alias postgresrun='docker run -p 0.0.0.0:5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres -d postgres'
alias prp='cd $PRIVATE_PROJECTS'
alias psh='/usr/local/microsoft/powershell/7/pwsh'
alias pwz='envify && echo -ne "$PASSWORD_ZIPS" | pbcopy'
alias py='av;ptpython;dv'
alias rags='ags -r rekordbox.xml -p "$HOME/Music/rekordbox"'
alias ram='mem'
alias record='asciinema rec'
alias refresh_homepage='kubectl rollout restart deployment -n personal-homepage personal-homepage-server-deployment'
alias reinstall_py='rm -rf "$VENV_PYTHON_3";pip install virtualenv && genvenv3 "$VENV_PYTHON_3" && av && pip install --upgrade pip && pip install -r $DOTFILESPATH/python/requirements.txt && ycminstall'
alias rekordboxxml='vi $HOME/Music/rekordbox/rekordbox.xml'
alias rm_brew_pkg='find "/opt/homebrew/Caskroom" -type f -name "*.pkg" -delete && rm -rf "$HOME/Library/Caches/Homebrew/downloads" && mkdir -p "$HOME/Library/Caches/Homebrew/downloads"'
alias rm_microsoft_autoupdater='sudo rm -rf "/Library/Application Support/Microsoft/MAU2.0"'
alias rm_node_modules='find "$(pwd)" -type d -name "node_modules" -exec rm -rf {} \;'
alias rmds="find . -type f -name '.DS_Store*' -delete"
alias rmjsdk='rm -rf "$HOME/.sdkman/archives/";mkdir -p "$HOME/.sdkman/archives/"'
alias rmlog="find . -type f -name '*.log' -delete"
alias rmmac='find /Volumes/SanDisk_1TB/ -type f -name "Icon?" -print -delete; dot_clean -nm /Volumes/SanDisk_1TB/'
alias rmnogit='git clean -dfx'
alias rmpy="find . -type f -name '*.pyc' -o -name '.cache' -o -name 'target' -o -name '.coverage' -o -name '__pycache__' -delete"
alias rmraycastclipboard='rm -rf "$HOME/Library/Caches/com.raycast.macos/Clipboard" && mkdir -p "$HOME/Library/Caches/com.raycast.macos/Clipboard"'
alias rmwin="find . -type f -name 'Thumbs.db' -or -name 'desktop.ini' -or -name '$RECYCLE.BIN' -delete"
alias rmzero='find . -size 0 | xargs rm'
alias rp='source $HOME/.bashrc'
alias rrr='rm -rf'
alias sconf='vi $HOME/.ssh/config'
alias sdkmanupdate='yes | sdk update;rmjsdk'
alias see="fzf --preview 'less {}'"
alias serials='envify && cd "$SERIALSDIR"'
alias shrug='print_and_copy "¯\_(ツ)_/¯"'
alias spacey='envify && 7z x "$ZIPS_DIR/Spacey.7z" -o"$DESKDIR" -p"$PASSWORD_ZIPS"'
alias spotify_clean='rm -rf /Users/$USERNAME/Library/Caches/com.spotify.client/Data'
alias spub='find $HOME/.ssh -name "id_*.pub" | while read file;do echo "$file:" && cat $file;done'
alias srevert='svn revert -R .'
alias srp='cd $WDIR/archive/siroop'
alias ss='sshrc'
alias sshfix='ssh-add --apple-use-keychain'
alias sshkeyadd='ssh-add --apple-use-keychain'
alias sshpasswd='ssh-keygen -p -f'
alias st='vi $DOTFILESPATH/setup'
alias superocd='sshkeyadd && ocd && update && rmraycastclipboard && rmmac && upallin "$HOME" && zgen update <<< "n" &> /dev/null && ck "$HOME" && create_backups'
alias t='lazygit'
alias telegram_deleter='av && $PRIVATE_PROJECTS/telegram-deleter/src/telegram_deleter.sh && dv'
alias thinking='print_and_copy 🤔'
alias tick='print_and_copy "✓"'
alias timer='echo "Timer started. Stop with Ctrl-D." && date && time cat && date'
alias tm='tmux'
alias tmk='tmux kill-session -t'
alias tml='tmux ls'
alias trp='tmux source-file ~/.tmux.conf' # reload tmux conf
alias tz='date "+%z %Z"'
alias unow='print_and_copy $(date +%s)'
alias update='macsoftwareupdate;bup;npm install -g npm;sdkmanupdate;vimpluginupdate'
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
### FUNCTIONS ###
find_java_sdk() {
    input_version="$*"
    matched_version=$(sdk list java |
      grep "installed" |
      fzf --filter="$input_version" |
      head -n 1 |
      awk -F'|' '{print $NF}' |
      sed 's/^ *//;s/ *$//')

    if [ ! -n "$matched_version" ]; then
        exit 1
    fi

    echo "$matched_version"
}
j() {
    if [ $# -eq 0 ]; then
        echo "Usage: j <version>"
        return 1
    fi

    local version=$(find_java_sdk "$@")
    if [[ -n "$version" ]]; then
        sdk use java "$version"
    else
        echo "No Java SDK version found for $*"
        return 1
    fi
}
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

