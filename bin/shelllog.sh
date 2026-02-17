RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RESET='\033[0m'

timestamp() {
    date +'%Y-%m-%d %H:%M:%S'
}

log() {
    echo -e "${GREEN}[$(timestamp)]${RESET} $*"
}

error() {
    echo -e "${RED}[$(timestamp)] ERROR:${RESET} $*" >&2
}

warn() {
    echo -e "${YELLOW}[$(timestamp)] WARN:${RESET} $*"
}

info() {
    echo -e "${GREEN}[$(timestamp)]${RESET} ${CYAN}INFO:${RESET} $*"
}

success() {
    echo -e "${GREEN}[$(timestamp)] ✓${RESET} $*"
}
