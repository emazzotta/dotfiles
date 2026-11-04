import json
import re
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

CTL = "-- bun /app/ctl.ts"
TOKEN = "ghp_demo_token_123"

BUN_SERVER = """\
FROM --platform=$BUILDPLATFORM oven/bun:1.4.4-alpine AS build
WORKDIR /src
RUN bun run build
FROM oven/bun:1.4.4-alpine
WORKDIR /app
COPY server server
EXPOSE 8080
HEALTHCHECK --interval=30s \\
  CMD wget -qO- http://127.0.0.1:8080/healthz
USER bun
CMD ["bun", "server/index.ts"]
"""
CADDY = """\
FROM caddy:2.11.7-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY src /app/src
# EXPOSE 9999 is a comment
EXPOSE 8080
"""
INHERITED = """\
FROM python:3.13-alpine AS builder
RUN uv sync
FROM python:3.13-alpine AS app
EXPOSE 8000
WORKDIR /app
CMD ["gunicorn", "app:app"]
FROM app AS dev
FROM app AS production
COPY --from=builder /opt/venv /opt/venv
"""
FILES = """\
FROM python:3.15-alpine AS builder
RUN python freeze.py
FROM alpine:3.24
WORKDIR /usr/src/site/
COPY --from=builder /usr/src/site/build /usr/src/site/build
COPY --from=builder /usr/src/site/version.json build/static/version.json
"""


@pytest.fixture
def demo_module(load_script):
    return load_script("demo")


def project(root: Path, files: dict) -> Path:
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content)
    return root


class TestDockerfile:
    def should_take_the_command_and_ports_of_the_last_stage(self, demo_module, tmp_path):
        stage = demo_module.final_stage(project(tmp_path, {"Dockerfile": BUN_SERVER}) / "Dockerfile")

        assert (stage.base, stage.expose, stage.command, stage.workdir) == (
            "oven/bun:1.4.4-alpine", [8080], ["bun", "server/index.ts"], "/app")

    def should_not_read_a_continued_healthcheck_as_the_command(self, demo_module, tmp_path):
        dockerfile = BUN_SERVER.replace('CMD ["bun", "server/index.ts"]\n', "")

        stage = demo_module.final_stage(project(tmp_path, {"Dockerfile": dockerfile}) / "Dockerfile")

        assert stage.command == []

    def should_inherit_from_an_earlier_stage(self, demo_module, tmp_path):
        stage = demo_module.final_stage(project(tmp_path, {"Dockerfile": INHERITED}) / "Dockerfile")

        assert (stage.base, stage.expose, stage.command) == ("python:3.13-alpine", [8000], ["gunicorn", "app:app"])

    def should_resolve_copy_destinations_against_the_workdir(self, demo_module, tmp_path):
        stage = demo_module.final_stage(project(tmp_path, {"Dockerfile": FILES}) / "Dockerfile")

        assert stage.copies == ["/usr/src/site/build", "/usr/src/site/build/static/version.json"]

    def should_drop_an_inherited_cmd_when_the_entrypoint_changes(self, demo_module, tmp_path):
        dockerfile = 'FROM a AS one\nCMD ["x"]\nFROM one\nENTRYPOINT ["bun", "main.ts"]\n'

        stage = demo_module.final_stage(project(tmp_path, {"Dockerfile": dockerfile}) / "Dockerfile")

        assert stage.command == ["bun", "main.ts"]


class TestPlan:
    @pytest.mark.parametrize("files,expected", [
        ({"Dockerfile": BUN_SERVER}, "BunServer(ctl_args=('--entry', 'server/index.ts'))"),
        ({"Dockerfile": BUN_SERVER.replace('["bun", "server/index.ts"]', '["bun", "run", "start"]')},
         "BunServer(ctl_args=('--script', 'start'))"),
        ({"Dockerfile": BUN_SERVER.replace('["bun", "server/index.ts"]', '["bun", "--smol", "a.ts"]')},
         "Container(port=8080)"),
        ({"Dockerfile": CADDY}, "Container(port=8080)"),
        ({"Dockerfile": INHERITED}, "Container(port=8000)"),
        ({"Dockerfile": FILES},
         "Files(candidates=('/usr/src/site/build', '/usr/src/site/build/static/version.json'))"),
        ({"package.json": '{"scripts": {"start": "bun server.ts"}}'}, "BunServer(ctl_args=('--script', 'start'))"),
        ({"package.json": '{"scripts": {"build": "bun build.ts"}}'}, "Static(site_dir=None, spa=False)"),
        ({}, "Static(site_dir=None, spa=False)"),
    ])
    def should_deploy_the_way_the_project_declares(self, demo_module, tmp_path, files, expected):
        plan = demo_module.plan_push(project(tmp_path, files), None, False)

        assert repr(plan).endswith(expected)

    def should_let_dir_and_spa_force_a_static_site(self, demo_module, tmp_path):
        plan = demo_module.plan_push(project(tmp_path, {"Dockerfile": CADDY}), "src", True)

        assert repr(plan).endswith("Static(site_dir='src', spa=True)")

    @pytest.mark.parametrize("text,expected", [
        ("My_Site", "my-site"), ("La Perla", "la-perla"), ("--x--", "x"), ("a" * 70, "a" * 58),
        ("a" * 57 + "-b", "a" * 57),
    ])
    def should_turn_a_directory_name_into_a_demo_name(self, demo_module, text, expected):
        assert demo_module.slug(text) == expected


class TestWorkload:
    def should_build_a_restricted_deployment_and_its_service(self, demo_module):
        deployment, service = demo_module.workload("shop", "ghcr.io/emazzotta/demo-shop:1", 8000)["items"]
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]

        assert deployment["metadata"]["name"] == service["metadata"]["name"] == "demo-shop"
        assert deployment["spec"]["selector"]["matchLabels"] == {"app": "demo", "demos.plexius.ch/name": "shop"}
        assert (container["image"], container["ports"][0]["containerPort"]) == ("ghcr.io/emazzotta/demo-shop:1", 8000)
        assert pod["automountServiceAccountToken"] is False
        assert pod["securityContext"]["runAsNonRoot"] is True
        assert container["securityContext"]["capabilities"] == {"drop": ["ALL"], "add": ["NET_BIND_SERVICE"]}
        assert service["spec"]["ports"] == [{"name": "http", "port": 8000, "targetPort": 8000}]


@pytest.fixture
def github_api():
    requests = []
    versions = [{"id": n, "created_at": f"2026-11-0{n}T00:00:00Z"} for n in (2, 3, 1)]

    class Handler(BaseHTTPRequestHandler):
        def _record(self, status, body=b""):
            requests.append((self.command, self.path, self.headers.get("Authorization")))
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._record(200, json.dumps(versions).encode())

        def do_DELETE(self):
            self._record(204)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield SimpleNamespace(url=f"http://127.0.0.1:{server.server_port}", requests=requests)
    server.shutdown()


@pytest.fixture
def demo(run_cli, tmp_path, github_api):
    work = tmp_path / "work"
    work.mkdir()
    files = {name: work / name for name in (
        "kubectl", "docker", "bun", "upload.tgz", "manifest.json", "creds", "leaks", "docker-host")}
    mocks = {
        "kubectl": f'''
echo "$*" >> "{files['kubectl']}"
name=$(echo "$*" | sed -E 's/.* push ([^ ]+).*/\\1/')
case "$*" in
    *" exec -i "*" push "*) cat > "{files['upload.tgz']}"; echo "$name: https://$name-demo.plexius.ch (release r1)" ;;
    *" exec "*" push "*) echo "$name: https://$name-demo.plexius.ch (release r2)" ;;
    *" list --json") echo '[{{"name": "alpha"}}, {{"name": "beta"}}]' ;;
    *"get deployment"*) echo "${{EXISTING:-}}" ;;
    *" apply "*) cat > "{files['manifest.json']}" ;;
    *"rollout status"*) [ -z "${{ROLLOUT_FAILS:-}}" ] || exit 1 ;;
    *"delete deployment,service"*) echo "${{DELETED:-}}" ;;
esac''',
        "docker": f'''
echo "$*" >> "{files['docker']}"
case "$1" in
    build) [ -z "${{BUILD_FAILS:-}}" ] || exit 1 ;;
    buildx) [ -z "${{NO_BUILDX:-}}" ] || exit 1 ;;
    context) echo unix:///mock/docker.sock ;;
    push) printf 'ghcr.io\\n' | docker-credential-demo get > "{files['creds']}"
          grep -rl "$DEMO_REGISTRY_SECRET" "$DOCKER_CONFIG" > "{files['leaks']}"
          echo "$DOCKER_HOST" > "{files['docker-host']}" ;;
    create) echo ctr1 ;;
    cp) case "$2" in
            "ctr1:/usr/src/site/build/index.html") exit 0 ;;
            "ctr1:/usr/src/site/build/.") mkdir -p "$3"; echo frozen > "$3/index.html" ;;
            *) exit 1 ;;
        esac ;;
esac''',
        "bun": f'''
echo "bun $*" >> "{files['bun']}"
mkdir -p dist && echo built > dist/index.html''',
        "envify": "return 1",
    }

    def _run(args, cwd=None, env=None):
        result = run_cli("demo", args, mock_bins=mocks, isolate_path=True, cwd=cwd or tmp_path, env_extra={
            "HOME": str(tmp_path),
            "KUBECONFIG": str(tmp_path / "no-kubeconfig"),
            "DEMO_SERVICE_ACCOUNT_TOKEN": str(tmp_path / "no-token"),
            "DEMO_CONTAINER_MARKER": str(tmp_path / "no-dockerenv"),
            "DEMO_GITHUB_API": github_api.url,
            "DOCKER_HOST": "",
            "GHCR_DEMO_TOKEN": TOKEN,
            **(env or {}),
        })
        result.calls = {key: path.read_text().splitlines() for key, path in files.items()
                        if key in ("kubectl", "docker", "bun") and path.exists()}
        result.files = files
        result.uploaded = _members(files["upload.tgz"]) if files["upload.tgz"].exists() else None
        result.github = github_api.requests
        return result

    return _run


def _members(archive: Path) -> list:
    with tarfile.open(archive, "r:gz") as tar:
        return sorted(name.removeprefix("./") for name in tar.getnames() if name not in (".", "./"))


def calls_matching(result, tool, fragment):
    return [call for call in result.calls.get(tool, []) if fragment in call]


class TestPushFiles:
    def should_publish_dist_as_a_static_site_named_after_the_directory(self, demo, tmp_path):
        site = project(tmp_path / "My_Site", {"dist/index.html": "hi", "README.md": "x"})

        result = demo(["push"], cwd=site)

        assert result.returncode == 0, result.stderr
        assert calls_matching(result, "kubectl", " push ") == [
            f"-n demos exec -i deployment/demos -c host {CTL} push my-site"]
        assert result.uploaded == ["index.html"]
        assert "my-site: https://my-site-demo.plexius.ch (release r1) in " in result.stdout

    def should_build_with_bun_first_when_package_json_has_a_build_script(self, demo, tmp_path):
        site = project(tmp_path / "shop", {"package.json": '{"scripts": {"build": "bun build.ts"}}'})

        result = demo(["push", "menu"], cwd=site)

        assert result.calls["bun"] == ["bun install --frozen-lockfile", "bun run build"]
        assert result.uploaded == ["index.html"]

    def should_run_the_entry_from_a_bun_dockerfile(self, demo, tmp_path):
        app = project(tmp_path / "scheila", {
            "Dockerfile": BUN_SERVER, "server/index.ts": "", "node_modules/x/i.js": "", ".env.local": "TOKEN=1",
            ".git/HEAD": "x", ".DS_Store": "",
        })

        result = demo(["push"], cwd=app)

        assert calls_matching(result, "kubectl", " push ") == [
            f"-n demos exec -i deployment/demos -c host {CTL} push scheila --entry server/index.ts"]
        assert result.uploaded == ["Dockerfile", "server", "server/index.ts"]

    def should_serve_the_files_an_image_without_a_port_ships(self, demo, tmp_path):
        site = project(tmp_path / "squido", {"Dockerfile": FILES})

        result = demo(["push"], cwd=site)

        assert result.returncode == 0, result.stderr
        assert any(call.startswith("build --platform linux/arm64") for call in result.calls["docker"])
        assert result.uploaded == ["index.html"]
        assert calls_matching(result, "docker", "rm ctr1") == ["rm ctr1"]

    def should_fail_when_there_is_nothing_to_publish(self, demo, tmp_path):
        result = demo(["push"], cwd=project(tmp_path / "empty", {"notes.txt": "x"}))

        assert result.returncode == 1
        assert "nothing to publish" in result.stderr
        assert calls_matching(result, "kubectl", " push ") == []

    def should_remove_a_container_the_name_ran_before(self, demo, tmp_path, github_api):
        site = project(tmp_path / "shop", {"index.html": "hi"})

        result = demo(["push"], cwd=site, env={"DELETED": "deployment.apps/demo-shop"})

        assert calls_matching(result, "kubectl", "delete deployment,service") == [
            "-n demos delete deployment,service -l demos.plexius.ch/name=shop --ignore-not-found -o name"]
        assert result.github == [("DELETE", "/user/packages/container/demo-shop", f"Bearer {TOKEN}")]


class TestPushContainer:
    def should_build_push_roll_out_and_route_the_image(self, demo, tmp_path):
        site = project(tmp_path / "plexius", {"Dockerfile": CADDY})

        result = demo(["push"], cwd=site)

        assert result.returncode == 0, result.stderr
        build = result.calls["docker"][0]
        image = re.search(r"-t (ghcr\.io/emazzotta/demo-plexius:\d{14})", build).group(1)
        assert build.startswith("build --platform linux/arm64 --build-arg VCS_REF=LOCAL")
        assert f"push --quiet {image}" in result.calls["docker"]
        assert json.loads(result.files["manifest.json"].read_text())["items"][0]["spec"]["template"]["spec"][
            "containers"][0]["image"] == image
        assert calls_matching(result, "kubectl", "rollout status") == [
            "-n demos rollout status deployment/demo-plexius --timeout=180s"]
        assert calls_matching(result, "kubectl", " push ") == [
            f"-n demos exec deployment/demos -c host {CTL} push plexius --image {image} --port 8080"]
        assert "plexius: https://plexius-demo.plexius.ch (release r2)" in result.stdout

    def should_hand_docker_the_token_without_writing_it_to_disk(self, demo, tmp_path):
        result = demo(["push"], cwd=project(tmp_path / "plexius", {"Dockerfile": CADDY}))

        assert json.loads(result.files["creds"].read_text()) == {"Username": "emazzotta", "Secret": TOKEN}
        assert result.files["leaks"].read_text() == ""
        assert result.files["docker-host"].read_text() == "unix:///mock/docker.sock\n"

    def should_keep_only_the_two_newest_images(self, demo, tmp_path):
        result = demo(["push"], cwd=project(tmp_path / "plexius", {"Dockerfile": CADDY}))

        assert [(method, path) for method, path, _ in result.github] == [
            ("GET", "/user/packages/container/demo-plexius/versions?per_page=100"),
            ("DELETE", "/user/packages/container/demo-plexius/versions/1"),
        ]

    def should_roll_back_an_update_that_never_gets_ready(self, demo, tmp_path):
        site = project(tmp_path / "plexius", {"Dockerfile": CADDY})

        result = demo(["push"], cwd=site, env={"ROLLOUT_FAILS": "1", "EXISTING": "deployment.apps/demo-plexius"})

        assert result.returncode == 1
        assert calls_matching(result, "kubectl", "rollout undo") == ["-n demos rollout undo deployment/demo-plexius"]
        assert "the previous release keeps serving" in result.stderr
        assert calls_matching(result, "kubectl", " push ") == []

    def should_remove_a_first_release_that_never_gets_ready(self, demo, tmp_path):
        result = demo(["push"], cwd=project(tmp_path / "plexius", {"Dockerfile": CADDY}), env={"ROLLOUT_FAILS": "1"})

        assert result.returncode == 1
        assert len(calls_matching(result, "kubectl", "delete deployment,service")) == 1
        assert "removed it" in result.stderr

    @pytest.mark.parametrize("env,message", [
        ({"BUILD_FAILS": "1", "NO_BUILDX": "1"}, "this docker has no buildx plugin"),
        ({"BUILD_FAILS": "1"}, "plexius: docker build failed, nothing was pushed"),
    ])
    def should_stop_before_pushing_when_the_build_fails(self, demo, tmp_path, env, message):
        result = demo(["push"], cwd=project(tmp_path / "plexius", {"Dockerfile": CADDY}), env=env)

        assert result.returncode == 1
        assert message in result.stderr
        assert not any(call.startswith("push") for call in result.calls["docker"])
        assert "kubectl" not in result.calls

    def should_explain_how_to_get_a_token_when_envify_has_none(self, demo, tmp_path):
        result = demo(["push"], cwd=project(tmp_path / "plexius", {"Dockerfile": CADDY}), env={"GHCR_DEMO_TOKEN": ""})

        assert result.returncode == 1
        assert "keyguard set GHCR_DEMO_TOKEN" in result.stderr
        assert "docker" not in result.calls


class TestGuards:
    @pytest.mark.parametrize("args", [
        ["push", "Bad_Name"], ["push", "a", "b"], ["frob"], ["logs"], ["logs", "a", "b"], ["rm"], ["list", "x"],
        ["logs", "a", "--spa"],
    ])
    def should_reject_bad_arguments_without_touching_the_cluster(self, demo, tmp_path, args):
        project(tmp_path, {"index.html": ""})

        result = demo(args)

        assert result.returncode in (1, 2)
        assert "kubectl" not in result.calls

    def should_refuse_to_run_inside_a_container(self, demo, tmp_path):
        marker = project(tmp_path, {"dockerenv": "", "index.html": ""}) / "dockerenv"

        result = demo(["push", "x"], env={"DEMO_CONTAINER_MARKER": str(marker)})

        assert result.returncode == 1
        assert "run it on the devbox or the Mac host" in result.stderr
        assert "kubectl" not in result.calls

    def should_use_the_pod_service_account_when_there_is_no_kubeconfig(self, run_cli, tmp_path):
        token = project(tmp_path, {"token": "t"}) / "token"
        mocks = {"kubectl": 'echo "api=${KUBERNETES_SERVICE_HOST:-none}"'}

        result = run_cli("demo", ["list"], mock_bins=mocks, isolate_path=True, env_extra={
            "HOME": str(tmp_path), "KUBECONFIG": str(tmp_path / "none"),
            "DEMO_SERVICE_ACCOUNT_TOKEN": str(token), "DEMO_CONTAINER_MARKER": str(tmp_path / "none")})

        assert result.stdout == "api=kubernetes.default.svc\n"


class TestRelay:
    @pytest.mark.parametrize("args,ctl_args", [
        (["list"], "list"), (["logs", "alpha"], "logs alpha"), (["rm", "alpha", "beta"], "rm alpha beta"),
    ])
    def should_relay_to_ctl_without_stdin(self, demo, args, ctl_args):
        result = demo(args)

        assert result.returncode == 0, result.stderr
        assert result.calls["kubectl"][0] == f"-n demos exec deployment/demos -c host {CTL} {ctl_args}"

    def should_delete_the_images_of_a_removed_container_demo(self, demo):
        result = demo(["rm", "shop"], env={"DELETED": "deployment.apps/demo-shop\nservice/demo-shop"})

        assert result.github == [("DELETE", "/user/packages/container/demo-shop", f"Bearer {TOKEN}")]


class TestComplete:
    @pytest.mark.parametrize("words,expected", [
        ([], ["push", "list", "logs", "rm"]),
        (["logs"], ["alpha", "beta"]),
        (["logs", "alpha"], []),
        (["rm", "alpha"], ["alpha", "beta"]),
        (["list"], []),
    ])
    def should_offer_the_next_word(self, demo, words, expected):
        result = demo(["--complete", *words])

        assert result.returncode == 0
        assert [line for line in result.stdout.splitlines() if line] == expected

    def should_offer_the_default_name_after_push(self, demo, tmp_path):
        result = demo(["--complete", "push"], cwd=project(tmp_path / "La Perla", {"index.html": ""}))

        assert result.stdout == "la-perla\n"
