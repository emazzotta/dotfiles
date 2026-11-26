import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

TOKEN = "schedule-token-for-tests"


class FakeBot:
    """The bot's schedule API as far as bot-schedule uses it: it records each request and answers as told."""

    def __init__(self) -> None:
        self.requests = []
        self.status = 200
        self.body = {"text": "Yours:\nS1, once Mon 30.11 12:00, by a session: check"}

    def handler(self):
        bot = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._answer()

            def do_POST(self):
                self._answer()

            def do_DELETE(self):
                self._answer()

            def _answer(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                bot.requests.append((self.command, self.path, self.headers.get("Authorization"), body))
                payload = json.dumps(bot.body).encode()
                self.send_response(bot.status)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        return Handler


@pytest.fixture
def bot():
    fake = FakeBot()
    server = ThreadingHTTPServer(("127.0.0.1", 0), fake.handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake
    server.shutdown()
    server.server_close()


@pytest.fixture
def schedule(load_script):
    return load_script("bot-schedule")


@pytest.fixture
def environ(bot, schedule):
    return {schedule.URL_NAME: bot.url, schedule.TOKEN_NAME: TOKEN}


@pytest.mark.parametrize("argv, request_line", [
    (["list"], ("GET", "/schedules", None)),
    (["add", "30.11", "12:00", "check", "the", "backups"], ("POST", "/schedules", {"text": "30.11 12:00 check the backups"})),
    (["rm", "S3"], ("DELETE", "/schedules/S3", None)),
])
def should_send_each_command_to_the_bot_with_the_bearer(schedule, bot, environ, capsys, argv, request_line):
    assert schedule.main(argv, environ) == 0

    method, path, body = request_line
    assert bot.requests == [(method, path, f"Bearer {TOKEN}", body)]
    assert capsys.readouterr().out.startswith("Yours:\nS1")


@pytest.mark.parametrize("status, body, message", [
    (400, {"error": "Say when, then the task."}, "Say when, then the task."),
    (404, {"text": "There is no schedule S9. /schedules lists them."}, "There is no schedule S9."),
    (423, {"error": "The owner locked the bot"}, "The owner locked the bot"),
    (502, {}, "the bot answered 502"),
])
def should_fail_with_the_bots_reason(schedule, bot, environ, capsys, status, body, message):
    bot.status, bot.body = status, body

    assert schedule.main(["rm", "S9"], environ) == 1

    assert message in capsys.readouterr().err


def should_name_the_token_when_the_bot_refuses_it(schedule, bot, environ, capsys):
    bot.status, bot.body = 401, {}

    assert schedule.main(["list"], environ) == 1

    err = capsys.readouterr().err
    assert schedule.TOKEN_NAME in err
    assert TOKEN not in err


def should_load_the_token_through_envify_when_none_is_exported(schedule, bot, monkeypatch):
    loads = []

    def values_via_shell(keys, environ):
        loads.append(keys)
        return {schedule.TOKEN_NAME: TOKEN}

    monkeypatch.setattr(schedule.envify, "values_via_shell", values_via_shell)

    assert schedule.main(["list"], {schedule.URL_NAME: bot.url}) == 0

    assert loads == [(schedule.TOKEN_NAME,)]
    assert bot.requests[0][2] == f"Bearer {TOKEN}"


def should_fail_when_envify_cannot_load_the_token(schedule, bot, monkeypatch, capsys):
    def refused(keys, environ):
        raise schedule.envify.EnvifyError("denied")

    monkeypatch.setattr(schedule.envify, "values_via_shell", refused)

    assert schedule.main(["list"], {schedule.URL_NAME: bot.url}) == 1

    assert "envify could not load" in capsys.readouterr().err
    assert bot.requests == []


def should_say_the_api_answers_on_the_dev_box_only_when_it_is_unreachable(schedule, capsys):
    environ = {schedule.URL_NAME: "http://127.0.0.1:1", schedule.TOKEN_NAME: TOKEN}

    assert schedule.main(["list"], environ) == 1

    assert schedule.UNREACHABLE_TEXT in capsys.readouterr().err


def should_use_the_in_cluster_service_by_default(schedule, monkeypatch):
    bases = []
    monkeypatch.setattr(schedule, "call", lambda base, *_args: bases.append(base) or schedule.Answer(200, {"text": ""}))

    schedule.main(["list"], {schedule.TOKEN_NAME: TOKEN})

    assert bases == ["http://telegram-bot.telegram-bot.svc.cluster.local:8081"]


@pytest.mark.parametrize("args", [[], ["add"], ["rm"], ["remove", "S1"]])
def should_refuse_a_bad_command_before_loading_any_secret(run_cli, tmp_path, args):
    result = run_cli("bot-schedule", args, mock_bins={"envify": f'echo called >> "{tmp_path / "calls"}"'})

    assert result.returncode == 2
    assert not (tmp_path / "calls").exists()


def should_list_its_subcommands_in_the_help(run_cli):
    result = run_cli("bot-schedule", ["--help"])

    assert result.returncode == 0
    assert "{list,add,rm}" in result.stdout
