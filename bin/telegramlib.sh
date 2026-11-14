#!/bin/bash
# Shared by tgf, tgm, tgv and tgup.
# Source as: source "$(dirname "${BASH_SOURCE[0]}")/telegramlib.sh"

TELEGRAM_API="https://api.telegram.org"
TELEGRAM_DEFAULT_CHAT="75804618"

telegram_usage_guard() {
    local usage
    usage="usage: $(basename "$0") $1"
    case "${2:-}" in
        -h|--help) echo "$usage"; exit 0 ;;
        "") echo "$usage" >&2; exit 1 ;;
    esac
}

telegram_load_bot_key() {
    if [[ -f "${DOTFILESPATH:-}/.env" ]]; then
        # shellcheck source=/dev/null
        source "${DOTFILESPATH}/.env"
    fi
    if [[ -z "${TELEGRAM_FILE_BOT_KEY:-}" ]]; then
        # shellcheck source=/dev/null
        source envify TELEGRAM_FILE_BOT_KEY
    fi
    [[ -n "${TELEGRAM_FILE_BOT_KEY:-}" ]]
}

# Sets TELEGRAM_CHAT and TELEGRAM_URL for the sourcing script, from an optional chat and bot key.
# shellcheck disable=SC2034
telegram_target() {
    local key="${2:-}"
    TELEGRAM_CHAT="${1:-$TELEGRAM_DEFAULT_CHAT}"
    if [[ -z "$key" ]]; then
        if ! telegram_load_bot_key; then
            echo "No Telegram bot key: pass one or store TELEGRAM_FILE_BOT_KEY" >&2
            return 1
        fi
        key="$TELEGRAM_FILE_BOT_KEY"
    fi
    TELEGRAM_URL="${TELEGRAM_API}/bot${key}"
}
