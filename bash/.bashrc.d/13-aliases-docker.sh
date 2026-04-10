#!/bin/bash
### COMPOSE / CORE ###
alias dc='docker-compose'
alias dps='docker ps'
alias dexe='docker-exec'
alias din='docker-inspect'

### TUI / INSPECTION ###
alias ctop='docker run -ti -v /var/run/docker.sock:/var/run/docker.sock quay.io/vektorlab/ctop'
alias dive='docker run -ti --rm  -v /var/run/docker.sock:/var/run/docker.sock wagoodman/dive'
alias dgui='docker run --rm -d -p 9000:9000 -v /var/run/docker.sock:/var/run/docker.sock portainer/portainer;echo "Open: http://localhost:9000"'

### CLEANUP ###
alias docker_prune='docker system prune -a -f --volumes'

### CONTAINERS ###
alias postgresrun='docker run -p 0.0.0.0:5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres -d postgres'
alias matrix='docker run --platform linux/amd64 -it --rm --log-driver none --net none --read-only --cap-drop=ALL willh/cmatrix'
alias cm='matrix'
