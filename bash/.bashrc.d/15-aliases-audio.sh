#!/bin/bash
### TAG FIX ###
alias audiofix='av && audiotags_manager --full-tag-optimizer'
alias audiofixall='av && find . -type f \( -name "*.mp3" -o -name "*.wav" -o -name "*.flac" \) -exec audiotags_manager --full-tag-optimizer {} \;'
alias af='audiofix'
alias afa='audiofixall'

### SPECTRAL ANALYSIS ###
alias as='audiospec'
alias asa='audiospecall'
alias audiospecall='find . -type f \( -name "*.mp3" -o -name "*.wav" -o -name "*.flac" \) -exec audiospec {} \;'

### REKORDBOX / DJ ###
alias rags='ags -r rekordbox.xml -p "$HOME/Music/rekordbox"'

### DOWNLOAD ###
alias yl='yt-dlp'
alias ylc='yt-dlp --cookies-from-browser safari'
