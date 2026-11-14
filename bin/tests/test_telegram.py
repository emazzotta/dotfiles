import pytest

API = "https://api.telegram.org"
DEFAULT_CHAT = "75804618"
ENVIFY_KEY = "key-from-envify"
HTTP_MOCK = 'printf "%s\\n" "$@" > "$HTTP_LOG"'
ENVIFY_MOCK = f'echo "$@" >> "$ENVIFY_LOG"\nexport TELEGRAM_FILE_BOT_KEY={ENVIFY_KEY}'
ENVIFY_FAILS = 'echo "$@" >> "$ENVIFY_LOG"\nreturn 1'
SENDERS = ["tgf", "tgm", "tgv"]
UPLOADS = [("tgf", "sendDocument", "document"), ("tgv", "sendVoice", "voice")]


@pytest.fixture
def telegram(run_cli, tmp_path):
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    http_log, envify_log = tmp_path / "http.log", tmp_path / "envify.log"

    def _run(script, *args, envify=ENVIFY_MOCK):
        return run_cli(
            script, list(args),
            env_extra={
                "DOTFILESPATH": str(dotfiles), "TELEGRAM_FILE_BOT_KEY": "",
                "HTTP_LOG": str(http_log), "ENVIFY_LOG": str(envify_log),
            },
            mock_bins={"http": HTTP_MOCK, "envify": envify},
        )
    _run.dotfiles = dotfiles
    _run.http_args = lambda: http_log.read_text().splitlines()
    _run.called_telegram = http_log.exists
    _run.loaded_a_key = envify_log.exists
    return _run


class TestTgm:
    def should_send_the_message_to_the_default_chat_with_the_key_from_envify(self, telegram):
        result = telegram("tgm", "hello there")

        assert result.returncode == 0, result.stderr
        assert telegram.http_args() == [
            "--body", f"{API}/bot{ENVIFY_KEY}/sendMessage", f"chat_id=={DEFAULT_CHAT}", "text==hello there",
        ]

    def should_send_the_message_to_the_named_chat(self, telegram):
        telegram("tgm", "hello", "42")

        assert "chat_id==42" in telegram.http_args()

    def should_use_the_given_key_without_loading_one(self, telegram):
        telegram("tgm", "hello", "42", "given-key")

        assert f"{API}/botgiven-key/sendMessage" in telegram.http_args()
        assert not telegram.loaded_a_key()

    def should_take_the_key_from_the_dotfiles_env_file_before_envify(self, telegram):
        (telegram.dotfiles / ".env").write_text("TELEGRAM_FILE_BOT_KEY=key-from-dotenv\n")

        telegram("tgm", "hello")

        assert f"{API}/botkey-from-dotenv/sendMessage" in telegram.http_args()
        assert not telegram.loaded_a_key()


@pytest.mark.parametrize("script,method,field", UPLOADS)
def should_upload_the_file_to_the_default_chat(telegram, script, method, field):
    result = telegram(script, "report.pdf")

    assert result.returncode == 0, result.stderr
    assert telegram.http_args() == [
        "--body", "-f", "POST", f"{API}/bot{ENVIFY_KEY}/{method}",
        f"chat_id=={DEFAULT_CHAT}", f"{field}@report.pdf",
    ]


@pytest.mark.parametrize("script", SENDERS)
class TestSenders:
    def should_print_usage_without_loading_a_key_when_nothing_is_given(self, telegram, script):
        result = telegram(script)

        assert result.returncode == 1
        assert "usage:" in result.stderr
        assert not telegram.loaded_a_key()
        assert not telegram.called_telegram()

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_print_usage_for_the_help_flag(self, telegram, script, flag):
        result = telegram(script, flag)

        assert result.returncode == 0
        assert "usage:" in result.stdout
        assert not telegram.called_telegram()

    def should_fail_without_calling_telegram_when_no_key_can_be_loaded(self, telegram, script):
        result = telegram(script, "payload", envify=ENVIFY_FAILS)

        assert result.returncode == 1
        assert "bot key" in result.stderr
        assert not telegram.called_telegram()


class TestTgup:
    def should_ask_for_updates_with_the_key_from_envify(self, telegram):
        result = telegram("tgup")

        assert result.returncode == 0, result.stderr
        assert telegram.http_args() == ["--body", f"{API}/bot{ENVIFY_KEY}/getUpdates"]

    def should_use_the_given_key_without_loading_one(self, telegram):
        telegram("tgup", "given-key")

        assert telegram.http_args() == ["--body", f"{API}/botgiven-key/getUpdates"]
        assert not telegram.loaded_a_key()

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_print_usage_for_the_help_flag(self, telegram, flag):
        result = telegram("tgup", flag)

        assert result.returncode == 0
        assert "usage:" in result.stdout
        assert not telegram.called_telegram()
