#!/bin/bash
### DNS ###
alias dnscheck='dig @1.1.1.1 ns +short'
alias dnsdhcp='ipconfig getpacket en0 | grep -i domain'
alias dnsflush='sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder'
alias dnsshow='scutil --dns'

### SSH ###
alias .sshrc='vi $HOME/.sshrc'
alias eak='vi $HOME/.ssh/authorized_keys'
alias ekh='vi $HOME/.ssh/known_hosts'
alias sconf='vi $HOME/.ssh/config'
alias nopw='ssh-copy-id'
alias ss='sshrc'
alias sshkeyadd='ssh-add --apple-use-keychain ~/.ssh/id_rsa; ssh-add --apple-use-keychain ~/.ssh/judocu01'
alias sshpasswd='ssh-keygen -p -f'
alias spub='find $HOME/.ssh/ -name "id_*.pub" | while read file;do echo "$file:" && cat $file;done'
alias killgpg='killall ssh-agent gpg-agent;gpgconf --kill all'

### NET ###
alias ping='prettyping --nolegend'
