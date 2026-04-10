#!/bin/bash
### BREW ###
alias brew='arch -arm64 brew'
alias bri='brew install'
alias bru='brew uninstall'
alias bup='echo "Updating Brew";git -C "$(brew --repo)" fetch --tags;brew update;brew upgrade;brew cu pin mixed-in-key;brew cu -afy --cleanup;brew cleanup;rm_brew_pkg'

### PYTHON / VENV ###
alias av='if [ -f "./venv/bin/activate"  ]; then source "./venv/bin/activate"; else source "$VENV_PYTHON_3/bin/activate"; fi'
alias dv='deactivate'
alias py='av;ptpython;dv'
alias genvenv3='virtualenv -p python3'
alias reinstall_py='rm -rf "$VENV_PYTHON_3";genvenv3 "$VENV_PYTHON_3" && av && pip install --upgrade pip && pip install -r $DOTFILESPATH/python/requirements.txt'
alias autopep='av;find . -name "*py" | xargs -I {} autopep8 -i {};dv'

### JAVA / SDKMAN ###
alias jv='java -version'
alias sdkmanupdate='yes | sdk update;rmjsdk'

### KUBERNETES ###
alias k='kubectl'
alias kc='kubeconf'
alias kn='kubens'

### TMUX ###
alias tm='tmux'
alias tmk='tmux kill-session -t'
alias tml='tmux ls'
alias trp='tmux source-file ~/.tmux.conf' # reload tmux conf

### FILE UTILS ###
alias ll='ls -lah'
alias ls='lsd'
alias l='printf "\033[H\033[2J"'
alias diff='icdiff'
alias grep='grep -i --color=auto'
alias see="fzf --preview 'less {}'"
alias vi='vim'

### ENCODING ###
alias asciitoutf='iconv -f US-ASCII -t utf-8'
alias isotoutf='iconv -f iso-8859-1 -t utf-8'
alias bom='echo -ne "\xEF\xBB\xBF"'

### FORMATTING ###
alias autoc='find . -iname *.h -o -iname *.c -o -iname *.cpp | xargs clang-format -style=file -i'

### SHORTCUTS ###
alias e='exit'
alias mc='m clean'
alias mci='mc install'

### DATE / TIME ###
alias now='print_and_copy $(date "+%Y-%m-%d-%H-%M-%S")'
alias unow='print_and_copy $(date +%s)'
alias tz='date "+%z %Z"'
alias timer='echo "Timer started. Stop with Ctrl-D." && date && time cat && date'

### MEMORY / MONITORING ###
alias ram='mem'

### FZF / EDITORS ###
alias psh='pwsh'
alias wsh='wpsh'

### CRON ###
alias ce='crontab_editor'
alias cronlist='crontab -l'

### YARN / NODE ###
alias y='yarn'
alias yarnupdate='curl --compressed -o- -L https://yarnpkg.com/install.sh | bash'
alias wscat='npx wscat'

### DOWNLOADS / ARCHIVES ###
alias dload='aria2c'
alias mpc='pwuncompress "$GDRIVEDIR/Dokumente/Zipped_PW/MPC.7z"'
alias spacey='pwuncompress "$ZIPS_DIR/Spacey.7z"'
alias pwz='source envify PASSWORD_ZIPS && echo -ne "$PASSWORD_ZIPS" | pbcopy'

### UPDATES ###
alias macsoftwareupdate='softwareupdate -i -a'
alias update='macsoftwareupdate;bup;npm install -g npm;sdkmanupdate;vimpluginupdate'

### MISC ###
alias encrypt='hashify'
alias f='source envify && open "$FOCUS_TRACK"'
alias lrr='print_and_copy $BOOKLIST_LINK'
alias localdbs='mysql -h 127.0.0.1 -u root <<< "SHOW DATABASES;"'
alias vskill='yes | killprocess "vsls-agent";yes | killprocess "Code Helper (Renderer)"'
alias telegram_deleter='av && $PRIVATE_PROJECTS/telegram-deleter/src/telegram_deleter.sh && dv'
alias judocuftp='lftp -e "open sftp://judocu"'
alias oc='$OPENCODE_PATH && make opencode'
