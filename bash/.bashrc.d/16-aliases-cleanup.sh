#!/bin/bash
### DISK USAGE ###
alias .du='du -hsx * | sort -rh | head -10'
alias node_modules_size='find . -name "node_modules" -type d -prune | xargs du -chs'
alias find_duplicate='find . -type f -maxdepth 4 -exec basename {} \; | sort -rn | uniq -d | while read dup; do find . -type f -maxdepth 4 -name "$dup"; done'

### PROJECT TRASH ###
alias jc='find . -name "build" -or -name "out" -or -name "generated" | xargs -I {} rm -rf {}'
alias rm_node_modules='find "$(pwd)" -type d -name "node_modules" -exec rm -rf {} \;'
alias rmpy="find . -type f -name '*.pyc' -o -name '.cache' -o -name 'target' -o -name '.coverage' -o -name '__pycache__' -delete"
alias rmlog="find . -type f -name '*.log' -delete"
alias rmds="find . -type f -name '.DS_Store*' -delete"
alias rmwin="find . -type f -name 'Thumbs.db' -or -name 'desktop.ini' -or -name '$RECYCLE.BIN' -delete"
alias rmzero='find . -size 0 | xargs rm'
alias rr='rm -rf'

### SDKMAN / BREW ###
alias rmjsdk='rm -rf "$HOME/.sdkman/archives/";mkdir -p "$HOME/.sdkman/archives/"'
alias rm_brew_pkg='find "/opt/homebrew/Caskroom" -type f -name "*.pkg" -delete && rm -rf "$HOME/Library/Caches/Homebrew/downloads" && mkdir -p "$HOME/Library/Caches/Homebrew/downloads"'

### MAC SYSTEM JUNK ###
alias rm_microsoft_autoupdater='sudo rm -rf "/Library/Application Support/Microsoft/MAU2.0"'
alias rmraycastclipboard='rm -rf "$HOME/Library/Caches/com.raycast.macos/Clipboard" && mkdir -p "$HOME/Library/Caches/com.raycast.macos/Clipboard"'
alias spotify_clean='rm -rf /Users/$USERNAME/Library/Caches/com.spotify.client/Data'
