#!/bin/bash
# Shared helpers for password-protected 7z operations via expect.
# Password is fed via env var to expect; never appears in argv.
# Source as: source "$(dirname "${BASH_SOURCE[0]}")/7zpw.sh"

_7zpw_is_keka() {
    command -v 7z >/dev/null 2>&1 || return 1
    local out
    out=$(7z 2>&1 | head -10) || true
    [[ "$out" == *"Modified by aone for Keka"* ]]
}

# Find the keka7zz PID launched by us. Keka.app spawns it detached (parent=launchd),
# so it's not in our process tree - we identify it as the one that wasn't running before.
# Polls for up to 3 seconds; returns empty if not found (e.g. expect already finished).
_7zpw_find_keka_pid() {
    local before="$1"
    local expect_pid="$2"
    local i pid current
    for ((i=0; i<30; i++)); do
        sleep 0.1
        kill -0 "$expect_pid" 2>/dev/null || return 0
        current=$(pgrep -f "^/Applications/Keka\.app/Contents/MacOS/keka7zz" 2>/dev/null || true)
        for pid in $current; do
            if ! grep -qw "$pid" <<< "$before"; then
                printf '%s\n' "$pid"
                return 0
            fi
        done
    done
}

# Run 7z with password fed via expect.
# Args:
#   $1   - max password prompts to try (1 = extract, 2 = compress).
#          Used as a max because Keka's compress only prompts once,
#          standard 7z's compress prompts twice (enter + confirm).
#   $2   - password value
#   $3+  - 7z arguments (must include -p without a value)
_7zpw_run() {
    local prompts="$1"
    local password="$2"
    shift 2

    local prompt is_keka=0
    if _7zpw_is_keka; then
        prompt="___KEKA___PASSWORD___KEKA___"
        is_keka=1
    else
        prompt="Enter password"
    fi

    local script
    script=$(mktemp /tmp/.7zpw_XXXXXX)
    trap 'rm -f "$script"' RETURN

    cat > "$script" << 'EXPECT'
set timeout -1
spawn 7z {*}$argv

expect $env(PROMPT)
log_user 0
send -- "$env(PASSWORD)\r"

# Confirmation prompt: standard 7z asks twice on compress, Keka asks once.
# Try briefly; move on if no second prompt appears. Catch swallows
# "spawn id not open" - Keka's shim can close the spawn fast on small inputs,
# and expect auto-closes the spawn id on EOF.
if {$env(PROMPTS) > 1} {
    set timeout 3
    catch {
        expect {
            $env(PROMPT) { send -- "$env(PASSWORD)\r" }
            timeout { }
        }
    }
    set timeout -1
}

# Keka echoes the password back as plain text; consume it before re-enabling output.
# Catch the spawn-already-closed error - on small archives the shim exits and
# expect auto-closes the spawn id before we get here.
if {$env(IS_KEKA) eq "1"} {
    set timeout 2
    catch {expect -re "\r?\n"}
    set timeout -1
}

log_user 1
catch {expect eof}
set rc 0
if {![catch {wait} result]} {
    set rc [lindex $result 3]
}
exit $rc
EXPECT

    # Snapshot existing keka7zz PIDs so we can identify the one we're about to launch.
    local keka_before=""
    [ "$is_keka" -eq 1 ] && keka_before=$(pgrep -f "^/Applications/Keka\.app/Contents/MacOS/keka7zz" 2>/dev/null || true)

    PASSWORD="$password" PROMPT="$prompt" PROMPTS="$prompts" IS_KEKA="$is_keka" \
        expect -- "$script" "$@" &
    local expect_pid=$!

    # Initial trap: kill expect immediately. Refined below once we know the keka7zz PID.
    # shellcheck disable=SC2064
    trap "kill $expect_pid 2>/dev/null" INT

    local keka_pid=""
    if [ "$is_keka" -eq 1 ]; then
        keka_pid=$(_7zpw_find_keka_pid "$keka_before" "$expect_pid")
        if [ -n "$keka_pid" ]; then
            # shellcheck disable=SC2064
            trap "kill -KILL $keka_pid 2>/dev/null; kill $expect_pid 2>/dev/null" INT
        fi
    fi

    local rc=0
    wait "$expect_pid" 2>/dev/null || rc=$?
    while kill -0 "$expect_pid" 2>/dev/null; do
        sleep 0.1
    done

    trap - INT
    return "$rc"
}
