[![Test](https://github.com/emazzotta/dotfiles/workflows/test/badge.svg)](https://github.com/emazzotta/dotfiles/actions)

# Dotfiles

This is a collection of my dotfiles.

## Install

```bash
cd ${HOME}/Desktop && \
  curl -fSsL https://github.com/emazzotta/dotfiles/archive/master.zip > master.zip && \
  unzip master.zip && \
  rm -rf master.zip && \
  mv dotfiles-master dotfiles && \
  cd dotfiles && \
  ./setup
```

## Private configuration

This repo is public, so host-specific values (internal hostnames, server addresses) live outside it in `~/.config/dotfiles/private.env` - a plain `KEY=value` file that shell scripts source and `bin/privateconf.py` parses. Point `DOTFILES_PRIVATE_ENV` elsewhere to override the location.

| Key | Read by |
|-----|---------|
| `NETWORK_DRIVE_SERVER_IP` | `leonardo_account`, `leonardo_drive`, `leopath` |
| `NETWORK_DRIVE_FOLDER` | `leonardo_account` (defaults to `Daten`) |
| `VM_DRIVE_MOUNT_POINT` | `leonardo_account` |
| `LEONARDO_STATUS_HOST` | `leonardo_start` |
| `HOST_ALIASES` | `host-resolver`, as `short-name:fqdn1,fqdn2;other-name:fqdn` |

Scripts that cannot work without a value fail naming the missing key. `leopath` and `host-resolver` fall back to their generic behaviour when the file is absent.
