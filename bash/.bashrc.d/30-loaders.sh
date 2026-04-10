#!/bin/bash
load "$DOTFILESPATH/autocomplete/custom_autocomplete"
load "$DOTFILESPATH/bin/colors"
test "$BASH_VERSION" && load "$HOME/.sshrc"

### NVM ###
export NVM_DIR="$HOME/.nvm"
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"
[ -s "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm" ] && \. "/opt/homebrew/opt/nvm/etc/bash_completion.d/nvm"

### SDKMAN ###
load "$SDKMAN_DIR/bin/sdkman-init.sh"
