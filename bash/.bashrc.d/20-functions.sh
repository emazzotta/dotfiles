#!/bin/bash
load() {
    [[ -f "$1" ]] && source "$1"
}

ep() {
    local rcd="$HOME/.bashrc.d"
    [ -d "$rcd" ] || rcd="$HOME/dotfiles/bash/.bashrc.d"

    case "${1:-}" in
        -h|--help)
            cat <<EOF
Usage: ep [<name>|-l|--list|-h|--help]

Browse or edit shell config chunks in $rcd.

  ep              Pick a file via fzf (falls back to \$EDITOR directory view)
  ep <name>       Jump to the definition of alias/export/function <name>
  ep -l, --list   List every definition grouped by file, via less
  ep -h, --help   Show this help
EOF
            return 0
            ;;
        -l|--list)
            {
                local f
                for f in "$rcd"/[0-9]*.sh; do
                    [ -r "$f" ] || continue
                    printf '\n\033[1;36m=== %s ===\033[0m\n' "$(basename "$f")"
                    grep -E '^(alias |export |[a-zA-Z_][a-zA-Z0-9_]*[[:space:]]*\(\))' "$f"
                done
            } | less -FRX
            return 0
            ;;
        "")
            if command -v fzf >/dev/null 2>&1; then
                local entries=()
                local f name content
                for f in "$rcd"/[0-9]*.sh; do
                    [ -r "$f" ] || continue
                    name=$(basename "$f")
                    content=$(tr '\n' ' ' < "$f" | tr -s ' ')
                    entries+=("$(printf '%-25s  %s' "$name" "$content")")
                done
                [ ${#entries[@]} -eq 0 ] && return 0
                local picked
                picked=$(printf '%s\n' "${entries[@]}" | fzf \
                    --preview "cat '$rcd/{1}'" \
                    --preview-window=right:60% \
                    --header 'edit which file? (matches name + content)' \
                    --height=60% | awk '{print $1}')
                [ -z "$picked" ] && return 0
                "$EDITOR" "$rcd/$picked"
            else
                "$EDITOR" "$rcd"
            fi
            source "$HOME/.bashrc"
            return 0
            ;;
        -*)
            printf 'unknown option: %s\n' "$1" >&2
            return 2
            ;;
        *)
            local name="$1"
            local esc
            esc=$(printf '%s' "$name" | sed 's/[][\.*^$+?(){}|/]/\\&/g')
            local hit
            hit=$(grep -HnE "^(alias ${esc}=|export ${esc}=|${esc}[[:space:]]*\(\))" \
                "$rcd"/[0-9]*.sh 2>/dev/null | head -1)
            if [ -z "$hit" ]; then
                printf 'no definition for: %s\n' "$name" >&2
                return 1
            fi
            local file line
            file="${hit%%:*}"
            line="${hit#*:}"
            line="${line%%:*}"
            "$EDITOR" "+$line" "$file"
            source "$HOME/.bashrc"
            return 0
            ;;
    esac
}

find_java_sdk() {
    sdk list java 2>/dev/null | grep -E "installed|local" | fzf --filter="$*" | head -n 1 | awk -F'|' '{gsub(/^ +| +$/, "", $NF); print $NF}'
}

j() {
    if [ $# -eq 0 ]; then
        echo "Usage: j <version>"
        return 1
    fi

    local version
    version=$(find_java_sdk "$@")
    if [[ -n "$version" ]]; then
        sdk use java "$version"
    else
        echo "No Java SDK version found for $*"
        return 1
    fi
}

superocd() {
    echo "Starting superocd sequence..."

    sshkeyadd && \
    ocd && \
    update && \
    rmraycastclipboard && \
    rmmac && \
    rm_old_gitlab_builds && \
    upallin "$HOME" && \
    zgen update <<< "n" &> /dev/null && \
    gck "$WDIR" && \
    source envify MAC_SUDO_PW GOOGLE_DOCUMENTS_API_KEY NOTION_API_KEY PASSWORD_ZIPS && \
    kill_unwanted_processes && \
    rm_launch_items && \
    gsheet_backup -e "1KZK4zhVIMSk-EHjCc_E0O3MJOYTFOCWb6awhigELBJ8" "$GDRIVEDIR/Dokumente/Docs/Automated_Backups" && \
    notion_backup "$GDRIVEDIR/Dokumente/Docs/Automated_Backups"

    local exit_code=$?
    return $exit_code
}
