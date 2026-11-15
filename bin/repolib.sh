#!/bin/bash

# bin/repolib.py reads this file the same way for Python scripts: change both.
rh_ignore_file="${HOME}/.config/repos/ignore"

rh_entries() {
    local section="${1}"
    local entry current=""
    [ -f "${rh_ignore_file}" ] || return 0
    while read -r entry || [ -n "${entry}" ]; do
        case "${entry}" in
            ""|"#"*) continue ;;
            "["*"]") current="${entry}"; continue ;;
        esac
        if [ "${current}" = "[${section}]" ]; then
            printf '%s\n' "${entry}"
        fi
    done < "${rh_ignore_file}"
}

rh_ignored() {
    local tool="${1}"
    local dir="${2}"
    local toplevel entry
    [ -f "${rh_ignore_file}" ] || return 1
    toplevel=$(git -C "${dir}" rev-parse --show-toplevel) || return 1
    while IFS= read -r entry; do
        # shellcheck disable=SC2254
        case "${toplevel}" in
            ${entry}|*/${entry}) return 0 ;;
        esac
    done < <(rh_entries "${tool}")
    return 1
}

rh_find_dirs() {
    local root="${1}"
    local entry
    local expression=(\( -type d -o -type l \) -print)
    while IFS= read -r entry; do
        expression=(-path "${entry}" -prune -o -path "*/${entry}" -prune -o "${expression[@]}")
    done < <(rh_entries prune)
    find "${root}" -mindepth 0 -maxdepth 3 "${expression[@]}"
}

rh_rebase_mode() {
    case "$1" in
        main|master) echo true ;;
        *) echo merges ;;
    esac
}

rh_longest_name() {
    local width=0
    local name
    while IFS= read -r name; do
        if [ "${#name}" -gt "${width}" ]; then
            width=${#name}
        fi
    done
    printf '%s' "${width}"
}

# The three functions below need prettyprint sourced first.

rh_repo_link() {
    local dir="$1"
    local root="$2"
    local path label
    path=$(git -C "${dir}" rev-parse --show-toplevel)
    label="${dir#"${root%/}"/}"
    if [ "${dir}" = "${root}" ]; then
        label="${path##*/}"
    fi
    hyperlink "file://${path}" "${YELLOW}${label}${RESET}"
}

rh_print_warnings() {
    local heading="$1"
    local file="$2"
    if [ ! -s "${file}" ]; then
        return 0
    fi
    echo
    error "${heading}"
    local warning
    while IFS= read -r warning; do
        substep_error "${warning}"
    done < "${file}"
}

rh_spin() {
    local pid="$1"
    local status_file="$2"
    local spinners='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
    local i=0
    while kill -0 "${pid}" 2>/dev/null; do
        local current
        current=$(cat "${status_file}" 2>/dev/null || echo "")
        printf "\033[2K\r  ${YELLOW}%s${RESET}  %s" "${spinners:$((i % 10)):1}" "${current}" >&2
        sleep 0.1
        i=$((i + 1))
    done
    printf "\r%-100s\r" "" >&2
}
