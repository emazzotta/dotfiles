#!/bin/bash
# Shared helpers for the docker-* wrapper scripts (docker-exec,
# docker-inspect, docker-cp, docker-debug).
# Source as: source "$(dirname "${BASH_SOURCE[0]}")/dockerlib.sh"

# Verify docker is on PATH. Optional second arg is a subcommand whose
# --help is also probed (e.g. 'debug' for Docker Desktop debug shell).
dh_require_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Error: docker not found" >&2
        exit 1
    fi

    local subcmd="${1:-}"
    if [ -n "$subcmd" ] && ! docker "$subcmd" --help >/dev/null 2>&1; then
        echo "Error: 'docker $subcmd' not available (requires Docker Desktop)" >&2
        exit 1
    fi
}

# Print the chosen running container name to stdout. Returns 1 if none.
# - 0 running         -> error
# - 1 running         -> auto-pick
# - 2+ running        -> picker (requires `picker` on PATH)
# Optional first arg overrides the picker header.
dh_pick_container() {
    local header="${1:-Select container:}"

    local running
    running=$(docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null)

    if [ -z "$running" ]; then
        echo "Error: no running containers found" >&2
        return 1
    fi

    local count
    count=$(echo "$running" | wc -l | tr -d ' ')

    if [ "$count" -eq 1 ]; then
        echo "$running" | cut -f1
        return 0
    fi

    if ! command -v picker >/dev/null 2>&1; then
        echo "Error: multiple containers running but no interactive picker backend found" >&2
        echo "Install: brew install fzf (or gum)" >&2
        echo "" >&2
        echo "Running containers:" >&2
        echo "$running" | column -t -s $'\t' >&2
        return 1
    fi

    local choices selected
    choices=$(echo "$running" | awk -F'\t' '{printf "%-30s %-35s %s\n", $1, $2, $3}')
    selected=$(echo "$choices" | picker --header "$header")

    if [ -z "$selected" ]; then
        echo "No container selected" >&2
        return 1
    fi

    echo "$selected" | awk '{print $1}'
}

# Exit with an error if the named container does not exist.
dh_assert_container_exists() {
    local container="$1"
    if ! docker inspect "$container" >/dev/null 2>&1; then
        echo "Error: container '$container' not found" >&2
        exit 1
    fi
}
