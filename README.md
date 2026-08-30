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

## Site configuration

Network-specific values live in `bin/site.env`, a plain `KEY=value` file read by
`bin/siteconf.py` and by the shell scripts. It ships with the Leonardo defaults,
so a fresh machine works after `leonardo_utils_installer` with nothing to fill in.

Three layers, highest first:

1. an environment variable of the same name, for a one-off
2. `~/.config/dotfiles/site.env`, for a permanent per-machine change
3. `bin/site.env`, the shipped defaults

Override key by key - anything the override file leaves out still comes from the
defaults. Edit `~/.config/dotfiles/site.env` rather than the installed
`site.env`, which `--force` overwrites on every update.

| Key | Read by |
|-----|---------|
| `NETWORK_DRIVE_SERVER_IP` | `leonardo_account`, `leonardo_drive`, `leopath` |
| `NETWORK_DRIVE_FOLDER` | `leonardo_account` |
| `VM_DRIVE_MOUNT_POINT` | `leonardo_account` |
| `LEONARDO_STATUS_HOST` | `leonardo_start` |
| `HOST_ALIASES` | `host-resolver`, as `short-name:fqdn1,fqdn2;other-name:fqdn` |

`DOTFILES_SITE_ENV` and `DOTFILES_SITE_DEFAULTS` relocate either file, which is
what the tests use.
