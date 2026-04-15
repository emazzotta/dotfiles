#!/bin/bash
### ANDROID ###
export ANDROID_AVD_HOME=$HOME/.android/avd
export ANDROID_HOME=$HOME/Library/Android/sdk
export ANDROID_SDK=$ANDROID_HOME
export ANDROID_SDK_ROOT=$ANDROID_HOME

### CORE PATHS ###
export WDIR="$HOME/Projects"
export PRIVATE_PROJECTS="$WDIR/private"
export DOTFILESPATH="$HOME/dotfiles"
export CUSTOM_BIN_DIR="$DOTFILESPATH/bin"
export GDRIVEDIR="$HOME/Google_Drive"
export DOCUMENTDIR="$GDRIVEDIR/Dokumente"
export DJ_DIR="$HOME/Music/01_DJ"

### PATH ###
export PATH="$CUSTOM_BIN_DIR:/opt/homebrew/bin:$PATH"
export PATH="$PATH:$HOME/.cargo/bin"
export PATH="$PATH:$HOME/.docker/bin"
export PATH="$PATH:$HOME/.local/bin"
export PATH="$PATH:$HOME/.lmstudio/bin"
export PATH="$PATH:$HOME/.yarn/bin:$HOME/.config/yarn/global/node_modules/.bin"
export PATH="$PATH:$ANDROID_HOME/emulator"
export PATH="$PATH:$ANDROID_HOME/platform-tools"
export PATH="$PATH:$ANDROID_HOME/tools"
export PATH="$PATH:$ANDROID_HOME/tools/bin"
export PATH="$PATH:$HOME/.bun/bin"

### TOOLCHAIN ###
export GCC_VERSION="15"
export CC="/opt/homebrew/bin/gcc-$GCC_VERSION"
export CXX="/opt/homebrew/bin/g++-$GCC_VERSION"
export CMAKE_C_COMPILER="/opt/homebrew/bin/gcc-$GCC_VERSION"
export CMAKE_CXX_COMPILER="/opt/homebrew/bin/g++-$GCC_VERSION"
export CMAKE_CXX_FLAGS="-std=c++17"
export CMAKE_CXX_STANDARD="17"
export CMAKE_EXE_LINKER_FLAGS="-lstdc++fs"
export CMAKE_MAKE_PROGRAM=$(which ninja)
export CMAKE_OPTIONS="-DUSE_SYSTEM_LIBCLANG=ON"

### DIRECTORIES ###
export APPDIR="/Applications"
export BOOKMARKDIR="$DOCUMENTDIR/Bookmarks"
export DESKDIR="$HOME/Desktop"
export DJ_TRACKS="$DJ_DIR/00_Collection"
export DOWNLOADDIR="$HOME/Downloads"
export GITDUMMYDIR="$PRIVATE_PROJECTS/gitdummy"
export KUBE_DIR="$HOME/.kube"
export MARKDOWNDIR="$DOCUMENTDIR/Markdown"
export OPENCODE_PATH="$PRIVATE_PROJECTS/opencode"
export PRIVATECOMMITSDIR="$PRIVATE_PROJECTS/private-commits"
export RECOMMENDED_READINGS="$MARKDOWNDIR/recommended_readings.md"
export VENV_PATH="$HOME/.venv"
export VENV_PYTHON_3="$VENV_PATH/python-3-venv"
export VIM_PLUGINS_DIR="$HOME/.vim_runtime/my_plugins"
export VIM_RUNTIME_DIR="$HOME/.vim_runtime"

### EDITOR ###
export EDITOR=/opt/homebrew/bin/vim
export VISUAL="$EDITOR"
export MANPAGER="less -X"
export LESS='-R'

### LOCALE ###
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LC_CTYPE=en_US.UTF-8
export LC_TYPE=en_US.UTF-8
export PYTHONIOENCODING='UTF-8'
export TERM="xterm-256color"
export XTERM="xterm-256color"

### COLORS ###
export CLICOLOR=1
export LSCOLORS="GxFxBxDxCxegedabagacad"
export LS_COLORS="di=1;36;40:ln=1;35;40:so=1;31;40:pi=1;33;40:ex=1;32;40:bd=34;46:cd=34;43:su=0;41:sg=0;46:tw=0;42:ow=0;43:"

### HISTORY / PROMPT ###
export HISTCONTROL="ignoreboth"
export HISTTIMEFORMAT="%Y-%m-%d %T "
export PROMPT_DIRTRIM=2
export KEYTIMEOUT=1

### TOOL CONFIG ###
export BREW_CASK_IGNORELIST="mixed-in-key\\|my-cask-to-pin"
export HOMEBREW_CASK_OPTS="--appdir=/Applications"
export CRONTAB_FILE="$DOTFILESPATH/cron/crontab"
export JAVA_HOME="$HOME/.sdkman/candidates/java/current"
export KEYGUARD_SECRETS_FILE="$DOCUMENTDIR/Keepass/keyguard.enc"
export POSH_THEMES_PATH="/opt/homebrew/opt/oh-my-posh/themes"
export SDKMAN_DIR="$HOME/.sdkman"
