[![Test](https://github.com/emazzotta/dotfiles/workflows/test/badge.svg)](https://github.com/emazzotta/dotfiles/actions)

# Dotfiles

This is a collection of my dotfiles.

## Install

The repository must live at `~/dotfiles`: the shell startup files and `PATH` read it from there. A fresh Mac needs the Xcode command line tools for `git` (`xcode-select --install`).

```bash
git clone https://github.com/emazzotta/dotfiles.git "${HOME}/dotfiles" && \
  "${HOME}/dotfiles/setup"
```
