#!/bin/bash
_load_bashrc_d() {
    if [ -n "${ZSH_VERSION:-}" ]; then
        setopt local_options null_glob
    fi
    local dir f
    dir="$HOME/.bashrc.d"
    [ -d "$dir" ] || dir="$HOME/dotfiles/bash/.bashrc.d"
    for f in "$dir"/[0-9]*.sh; do
        [ -r "$f" ] && . "$f"
    done
}
_load_bashrc_d
unset -f _load_bashrc_d
