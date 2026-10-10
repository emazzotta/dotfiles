#!/bin/bash

rh_ignore_file="${HOME}/.config/repos/ignore"

rh_ignored() {
    local tool="${1}"
    local dir="${2}"
    local toplevel entry section=""
    [ -f "${rh_ignore_file}" ] || return 1
    toplevel=$(git -C "${dir}" rev-parse --show-toplevel) || return 1
    while read -r entry || [ -n "${entry}" ]; do
        case "${entry}" in
            ""|"#"*) continue ;;
            "["*"]") section="${entry}"; continue ;;
        esac
        if [ "${section}" != "[${tool}]" ]; then
            continue
        fi
        # shellcheck disable=SC2254
        case "${toplevel}" in
            ${entry}|*/${entry}) return 0 ;;
        esac
    done < "${rh_ignore_file}"
    return 1
}
