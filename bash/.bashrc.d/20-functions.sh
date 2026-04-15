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

  ep              Fuzzy-search file names and contents via fzf; jump to picked line
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
                local lines
                lines=$(awk '
                    FNR == 1 { printf "%s:1:# --- %s ---\n", FILENAME, FILENAME }
                    { printf "%s:%d:%s\n", FILENAME, FNR, $0 }
                ' "$rcd"/[0-9]*.sh 2>/dev/null)
                [ -z "$lines" ] && return 0
                local picked
                picked=$(printf '%s' "$lines" | fzf \
                    --delimiter=: \
                    --with-nth=1,3.. \
                    --preview "awk -v n={2} 'NR>=n-10 && NR<=n+20 {printf \"%s%4d: %s\n\", (NR==n?\"> \":\"  \"), NR, \$0}' {1}" \
                    --preview-window=right:60% \
                    --header 'fuzzy-search file or content; enter opens at line' \
                    --height=80%)
                [ -z "$picked" ] && return 0
                local file line
                file="${picked%%:*}"
                line="${picked#*:}"
                line="${line%%:*}"
                "$EDITOR" "+$line" "$file"
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
