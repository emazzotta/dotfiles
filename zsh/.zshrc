#
# Executes commands at the start of an interactive session.
#
# Authors:
#   Sorin Ionescu <sorin.ionescu@gmail.com>
#
if [[ -s "${ZDOTDIR:-$HOME}/.zprezto/init.zsh" ]]; then
  source "${ZDOTDIR:-$HOME}/.zprezto/init.zsh"
fi

source "${HOME}/.bashrc"

source "$HOME/.zgen/zgen.zsh"
load "$DOTFILESPATH/bin/zshaddhistory"
load "$DOTFILESPATH/autocomplete/zsh/_kubectl"
load "$DOTFILESPATH/autocomplete/zsh/_bun"
if ! zgen saved; then
    zgen prezto
    zgen prezto git
    zgen prezto history-substring-search
    zgen prezto syntax-highlighting
    zgen load "$DOTFILESPATH/autocomplete/zsh"
    zgen load junegunn/fzf shell
    zgen load zsh-users/zsh-syntax-highlighting
    zgen load tarruda/zsh-autosuggestions
    zgen save
    compinit
fi

export PATH="$HOME/.yarn/bin:$HOME/.config/yarn/global/node_modules/.bin:$PATH"
