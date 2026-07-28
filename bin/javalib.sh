#!/bin/bash
# Shared helpers for picking a Java SDK through SDKMAN.
# Backs the `j` shell function and the leorun script.
# Source as: source "${BASH_SOURCE[0]%/*}/javalib.sh"

# Run a command with the caller's `set -eu` lifted, then restore. Both
# sdkman-init.sh and the `sdk` function it defines read unset variables
# (sdkman-main.sh:79 reads SDKMAN_OFFLINE_MODE), which aborts a `set -u` script.
jh_relaxed() {
    local jh_flags="$-" jh_status=0
    set +eu
    "$@" || jh_status=$?
    case "$jh_flags" in
        *e*) set -e ;;
    esac
    case "$jh_flags" in
        *u*) set -u ;;
    esac
    return "$jh_status"
}

# Define the `sdk` function unless the shell already has it.
jh_ensure_sdkman() {
    if command -v sdk >/dev/null 2>&1; then
        return 0
    fi

    local init="${SDKMAN_DIR:-$HOME/.sdkman}/bin/sdkman-init.sh"
    if [ ! -f "$init" ]; then
        echo "Error: sdkman not found at $init" >&2
        return 1
    fi

    # shellcheck disable=SC1090
    jh_relaxed source "$init"
}

# Print the identifier of the newest installed Java matching the query
# (jh_find_sdk 25 -> 25.0.3-tem). Reads the candidates directory directly:
# `sdk list java` curls the SDKMAN broker on every call.
# Returns 1 when nothing matches.
jh_find_sdk() {
    local query="$*"
    local candidates="${SDKMAN_CANDIDATES_DIR:-${SDKMAN_DIR:-$HOME/.sdkman}/candidates}/java"

    if [ ! -d "$candidates" ]; then
        echo "Error: no installed Java candidates in $candidates" >&2
        return 1
    fi

    local nl entry name matches=""
    nl=$'\n'
    for entry in "$candidates"/*/; do
        name="${entry%/}"
        name="${name##*/}"
        if [ "$name" = "current" ] || [ "$name" = '*' ]; then
            continue
        fi
        case "$name" in
            *"$query"*) matches="${matches}${name}${nl}" ;;
        esac
    done

    if [ -z "$matches" ]; then
        return 1
    fi

    printf '%s' "$matches" | sort -t. -k1,1nr -k2,2nr -k3,3nr | awk 'NR == 1'
}

# Switch the current shell to the newest installed Java matching the query.
jh_use() {
    local identifier
    if ! identifier=$(jh_find_sdk "$@"); then
        echo "No Java SDK version found for $*" >&2
        return 1
    fi

    jh_ensure_sdkman || return 1
    jh_relaxed sdk use java "$identifier"
}
