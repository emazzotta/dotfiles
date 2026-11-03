# Read by every zsh, including the non-interactive `zsh -c` that sshd runs for a remote command such as
# web-terminal's tmux on the Mac. .zshrc builds the full PATH for interactive shells only.
if [[ "$OSTYPE" == darwin* ]]; then
  typeset -U path
  path=("$HOME/dotfiles/bin" /opt/homebrew/bin "$HOME/.bun/bin" $path)

  # sshd hands its sessions no agent, and a tmux attached from one drops SSH_AUTH_SOCK from new panes.
  if [[ ! -S "$SSH_AUTH_SOCK" ]]; then
    () { if (( $# )); then export SSH_AUTH_SOCK="$1"; fi } /var/run/com.apple.launchd.*/Listeners(N=)
  fi

  # Terminal.app sets LANG, sshd does not, and pbcopy without it copies UTF-8 as MacRoman.
  if [[ -z "$LANG" ]]; then
    export LANG=en_US.UTF-8
  fi
fi
