#!/bin/bash

DIR=$(dirname "$0")
cd "$DIR"

if [ "$(uname)" == "Darwin" ]; then
    bundle install --gemfile=./Gemfile
    ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

    brew tap homebrew/bundle
    brew bundle --file="./Brewfile"

    curl -s "https://get.sdkman.io" | bash

    # Set Dock items
    OLDIFS=$IFS
    IFS=''
    apps=(
        iTerm
        'Google Chrome'
        'IntelliJ IDEA'
        Slack
        Spotify
    )
    dockutil --no-restart --remove all ${HOME}
    for app in "${apps[@]}"; do
        echo "Keeping $app in Dock"
        dockutil --no-restart --add /Applications/$app.app ${HOME}
    done
    killall Dock
    IFS=$OLDIFS

    ./macos

    npm install -g cash-cli
    npm install -g eslint
    npm install -g yarn
    pip install --upgrade pip
    pip install autopep8
    pip install awscli
    pip install bpython
    pip install virtualenv
    sudo xcode-select --install
    sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
    git clone -C "${HOME}" https://github.com/tarjoilija/zgen.git
    git clone --recursive https://github.com/sorin-ionescu/prezto.git ${ZDOTDIR:-$HOME}/.zprezto
    git clone --depth=1 https://github.com/amix/vimrc.git "${HOME}/.vim_runtime"
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:Glench/Vim-Jinja2-Syntax.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:OmniSharp/omnisharp-vim.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:Valloric/YouCompleteMe.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:ap/vim-css-color.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:benmills/vimux.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:editorconfig/editorconfig-vim.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:jceb/vim-orgmode.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:junegunn/fzf.vim.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:mattn/emmet-vim.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:tomlion/vim-solidity.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:tpope/vim-dispatch.git
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:vim-airline/vim-airline
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone git@github.com:tmux-plugins/vim-tmux-focus-events.git
    git -C "${HOME}/.vim_runtime/sources_non_forked/YouCompleteMe" submodule update --init --recursive
    git -C "${HOME}/.vim_runtime/sources_non_forked/omnisharp-vim" submodule update --init --recursive
    git -C "${HOME}/.vim_runtime/sources_non_forked" clone https://github.com/OmniSharp/omnisharp-server.git
    git -C "${HOME}/.vim_runtime/sources_non_forked/omnisharp-server" submodule update --init --recursive
    cd "${HOME}/.vim_runtime/sources_non_forked/omnisharp-server" && xbuild || true
    cd "${HOME}/.vim_runtime/sources_non_forked/YouCompleteMe" \
        && ./install.py --clang-completer --gocode-completer --tern-completer --omnisharp-completer || true
else
    sudo apt-get update && sudo apt-get -y upgrade && sudo apt-get -y dist-upgrade
    sudo apt-get install -y \
        bc \
        bridge-utils \
        build-essential \
        curl \
        docker \
        git \
        htop \
        mailutils \
        postgresql \
        python \
        python-pip \
        rungetty \
        sudo \
        sysstat \
        tee \
        tmux \
        unzip \
        vim \
        virtualbox-guest-utils \
        wget \
        zsh

    sudo adduser emanuele vboxsf
    sudo vi /etc/default/grub
    sudo vi /etc/init/tty1.conf > exec /sbin/rungetty --autologin emanuele tty1
    git clone --recursive https://github.com/sorin-ionescu/prezto.git "${ZDOTDIR:-$HOME}/.zprezto"
    zsh
    setopt EXTENDED_GLOB
    for rcfile in "${ZDOTDIR:-$HOME}"/.zprezto/runcoms/^README.md; do
        ln -s "$rcfile" "${ZDOTDIR:-$HOME}/.${rcfile:t}"
    done
    chsh -s /bin/zsh

    sudo curl -L https://github.com/docker/compose/releases/download/1.22.0/docker-compose-`uname -s`-`uname -m` > /usr/local/bin/docker-compose
    sudo mkdir -p /etc/systemd/system/docker.service.d
    sudo printf "[Service]nExecStart=nExecStart=/usr/bin/dockerd --storage-driver=overlay" > /etc/systemd/system/docker.service.d/
    sudo service docker start
    sudo chmod +x /usr/bin/docker-compose
    sudo timedatectl set-timezone Etc/UTC
    sudo echo 0 | sudo tee /proc/sys/net/ipv4/conf/all/accept_redirects
fi
