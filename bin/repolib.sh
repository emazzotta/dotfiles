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
