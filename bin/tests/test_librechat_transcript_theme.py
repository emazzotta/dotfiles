import pytest


@pytest.fixture
def mod(load_script):
    return load_script("librechat-transcript-theme")


class TestInjectTheme:
    def should_insert_style_block_before_head_close(self, mod):
        html = "<html><head><style>body{}</style></head><body></body></html>"
        result, changed = mod.inject_theme(html)
        assert changed is True
        assert f'id="{mod.THEME_ID}"' in result
        assert result.index(mod.THEME_ID) < result.index("</head>")

    def should_win_cascade_by_appearing_after_generator_style(self, mod):
        html = "<head><style>generator</style></head><body></body>"
        result, _ = mod.inject_theme(html)
        assert result.index("generator") < result.index(mod.THEME_ID)

    def should_be_idempotent_when_already_themed(self, mod):
        html = "<head><style>x</style></head><body></body>"
        once, changed_once = mod.inject_theme(html)
        twice, changed_twice = mod.inject_theme(once)
        assert changed_once is True
        assert changed_twice is False
        assert once == twice
        assert once.count(f'id="{mod.THEME_ID}"') == 1

    def should_fall_back_to_body_when_no_head_close(self, mod):
        html = "<body><p>hi</p></body>"
        result, changed = mod.inject_theme(html)
        assert changed is True
        assert mod.THEME_ID in result
        assert result.index(mod.THEME_ID) < result.index("<p>hi")

    def should_prepend_when_neither_head_nor_body_present(self, mod):
        html = "<div>bare fragment</div>"
        result, changed = mod.inject_theme(html)
        assert changed is True
        assert result.startswith("<style")

    def should_carry_librechat_role_selectors(self, mod):
        for selector in [".message.user", ".message.assistant",
                         ".message.thinking", ".message.tool_use"]:
            assert selector in mod.LIBRECHAT_THEME_CSS

    def should_inject_companion_script(self, mod):
        html = "<head></head><body></body>"
        result, _ = mod.inject_theme(html)
        assert f'id="{mod.SCRIPT_ID}"' in result
        assert "<script" in result and "</script>" in result

    def should_carry_fold_and_expand_behaviour_in_script(self, mod):
        assert "openAssistantReplies" in mod.LIBRECHAT_THEME_JS
        assert ".message.assistant details" in mod.LIBRECHAT_THEME_JS
        assert "foldTheme" in mod.LIBRECHAT_THEME_JS
        assert "prefers-color-scheme" in mod.LIBRECHAT_THEME_JS

    def should_scroll_to_top_imperatively_because_sticky_header_kills_the_anchor(self, mod):
        assert "fixScrollTop" in mod.LIBRECHAT_THEME_JS
        assert "a.scroll-top" in mod.LIBRECHAT_THEME_JS
        assert "preventDefault" in mod.LIBRECHAT_THEME_JS
        assert "window.scrollTo" in mod.LIBRECHAT_THEME_JS

    def should_guard_scroll_top_against_double_binding(self, mod):
        assert "dataset.lcScrollTop" in mod.LIBRECHAT_THEME_JS

    def should_run_scroll_top_fix_on_load(self, mod):
        run_body = mod.LIBRECHAT_THEME_JS.split("function run()")[1].split("}")[0]

        assert "fixScrollTop()" in run_body


class TestIsThemed:
    @pytest.mark.parametrize("html,expected", [
        ('<style id="librechat-theme">x</style>', True),
        ("<style id='librechat-theme'>x</style>", True),
        ("<style>plain</style>", False),
        ("", False),
    ])
    def should_detect_existing_theme(self, mod, html, expected):
        assert mod.is_themed(html) is expected


class TestProcessFile:
    def should_write_theme_into_file(self, mod, tmp_path):
        f = tmp_path / "t.html"
        f.write_text("<head></head><body></body>", encoding="utf-8")
        assert mod.process_file(f) is True
        assert mod.THEME_ID in f.read_text(encoding="utf-8")

    def should_not_rewrite_already_themed_file(self, mod, tmp_path):
        f = tmp_path / "t.html"
        f.write_text("<head></head><body></body>", encoding="utf-8")
        mod.process_file(f)
        assert mod.process_file(f) is False
