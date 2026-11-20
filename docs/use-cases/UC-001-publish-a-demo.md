# UC-001 Publish a Demo

| | |
|---|---|
| Primary actor | Developer |
| Supporting actors | Mac (keyguard bridge, Docker Desktop), home cluster, GHCR |
| Goal | Get a prototype online at `https://<name>-demo.plexius.ch` with one command |
| State | Basic Flow Enabled; A4 to A6 fulfilled |

Tool: `bin/demo`. Operations guide: personal-infra `docs/runbooks/demos.md`.

## Basic Flow

A project whose Dockerfile `EXPOSE`s a port, pushed where a docker daemon answers.

1. The Developer runs `demo push [name]` in the project.
2. `demo` reads the Dockerfile and chooses a container demo.
3. `demo` builds the image for `linux/arm64`.
4. `demo` pushes the image to GHCR.
5. `demo` rolls out Deployment and Service `demo-<name>`.
6. `demo` points the route at the service and prints the URL.

The use case ends.

## Alternate Flows

| ID | Name | Tests |
|---|---|---|
| A1 | Static files | none tagged yet |
| A2 | Bun server | none tagged yet |
| A3 | Image of files | none tagged yet |
| A4 | No docker daemon: the Mac pushes | `TestBridge`, `test_macbridge.py` |
| A5 | The push on the Mac fails | `TestBridge` |
| A6 | The Mac refuses the request | `TestBridge` |
| A7 | Rollout not ready | none tagged yet |

### A4 No docker daemon: the Mac pushes

At step 3, no docker daemon answers, and the project sits on a share from the Mac.

1. `demo` maps the project to its Mac path.
2. `demo` sends the Mac path and the demo name to the bridge endpoint `demo-push`.
3. The Developer approves the bridge call with Touch ID.
4. On the Mac, `demo --bridge-push` runs steps 2 to 6 for that project.
5. `demo` prints the Mac's log, which ends with the URL.

A plan without a docker build (A1, A2) stays in the container.

### A5 The push on the Mac fails

`demo` prints the Mac's log and the error, and exits with status 1.

### A6 The Mac refuses the request

The Mac stops before the build, with the reason on stdout, when the request is not JSON with both fields, the name is not a valid demo name, or BR-001 fails.

## Business Rules

| ID | Rule |
|---|---|
| BR-001 | The Mac builds only an existing folder that resolves inside `~/Projects` or `~/Desktop`. |
| BR-002 | The bridge request holds only the Mac path and the demo name; the Mac loads every secret itself. |
| BR-003 | On the Mac, `demo` keeps launchd's PATH first, adds the Homebrew, Docker and dotfiles folders after it, and uses `~/.kube/personal-infra.yaml` when `KUBECONFIG` is not set. |
| BR-004 | On the Mac, the whole log goes to stdout, because the bridge returns only stdout on success. |

## Glossary

| Term | Meaning |
|---|---|
| Mac share | A folder that Docker Desktop shares from the Mac's `/Users` into the container |
| Bridge | keyguard-server's HTTP endpoints, each a fixed command on the Mac behind one Touch ID |
| Demo name | A DNS label of at most 58 characters, the default being the git toplevel's folder name |
