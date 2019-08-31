# Dotfiles

This is a collection of my dotfiles.

## Install

```bash
cd ${HOME} && \
  curl -fSsL https://github.com/emazzotta/dotfiles/archive/master.zip > master.zip && \
  unzip master.zip && \
  rm -rf master.zip && \
  mv dotfiles-master dotfiles && \
  cd dotfiles && \
  ./setup
```
