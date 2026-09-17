import platform

import pytest

RAW_PAGE = (
    "<|det|>title [357, 135, 642, 155]<|/det|>Unlimited OCR Works\n"
    "<|det|>text [10, 20, 30, 40]<|/det|>First line\n"
    "second line\n"
    "\n"
    "<|det|>image [0, 0, 1, 1]<|/det|>\n"
    "<|det|>text [10, 50, 30, 60]<|/det|>Closing paragraph\n"
)
CLEAN_PAGE = "Unlimited OCR Works\n\nFirst line\nsecond line\n\nClosing paragraph"


@pytest.fixture
def mod(load_script):
    return load_script("ocr")


class FakeEngine:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def parse(self, images, profile):
        self.calls.append((list(images), profile))
        return self.outputs.pop(0)


class TestBannedTokens:
    def test_should_ban_the_token_that_followed_the_current_prefix_earlier_in_the_window(self, mod):
        sequence = [1, 2, 3, 9, 1, 2]

        assert mod.banned_tokens(sequence, ngram_size=3, window=10) == {3}

    def test_should_ban_every_continuation_seen_for_the_prefix(self, mod):
        sequence = [1, 2, 3, 1, 2, 4, 1, 2]

        assert mod.banned_tokens(sequence, ngram_size=3, window=100) == {3, 4}

    def test_should_ban_nothing_when_the_sequence_is_shorter_than_the_ngram(self, mod):
        assert mod.banned_tokens([1, 2], ngram_size=3, window=10) == set()

    def test_should_ignore_ngrams_that_start_before_the_window(self, mod):
        sequence = [1, 2, 3, 9, 9, 9, 9, 1, 2]

        assert mod.banned_tokens(sequence, ngram_size=3, window=4) == set()

    def test_should_ban_every_token_in_the_window_when_the_ngram_size_is_one(self, mod):
        assert mod.banned_tokens([5, 6, 7], ngram_size=1, window=2) == {6, 7}


class TestNoRepeatNgramGuard:
    def test_should_set_banned_logits_to_minus_infinity_and_leave_the_rest_untouched(self, mod):
        mx = pytest.importorskip("mlx.core")
        guard = mod.NoRepeatNgramGuard(ngram_size=2, window=10)
        tokens = mx.array([4, 7, 4])
        logits = mx.zeros((1, 10))

        result = guard(tokens, logits)

        assert result[0, 7].item() == float("-inf")
        assert result[0, 3].item() == 0.0

    def test_should_return_logits_unchanged_when_nothing_is_banned(self, mod):
        mx = pytest.importorskip("mlx.core")
        guard = mod.NoRepeatNgramGuard(ngram_size=2, window=10)
        logits = mx.zeros((1, 4))

        result = guard(mx.array([1, 2, 3]), logits)

        assert result.tolist() == [[0.0, 0.0, 0.0, 0.0]]


class TestStripLayoutMarkers:
    def test_should_keep_the_block_text_and_drop_the_detection_tags(self, mod):
        result = mod.strip_layout_markers(RAW_PAGE)

        assert "<|det|>" not in result
        assert "Unlimited OCR Works" in result

    def test_should_separate_blocks_with_a_blank_line_and_keep_a_block_on_consecutive_lines(self, mod):
        assert mod.strip_layout_markers(RAW_PAGE) == CLEAN_PAGE

    def test_should_drop_image_blocks(self, mod):
        assert "image" not in mod.strip_layout_markers(RAW_PAGE)

    def test_should_accept_a_detection_tag_without_a_bounding_box(self, mod):
        assert mod.strip_layout_markers("<|det|>text<|/det|>Bare\n") == "Bare"


class TestPages:
    def test_should_split_one_shot_output_on_page_markers_and_drop_empty_segments(self, mod):
        raw = "<PAGE>\nAlpha\n<PAGE>\nBeta\n"

        assert mod.split_pages(raw) == ["Alpha", "Beta"]

    def test_should_join_a_single_page_without_a_page_comment(self, mod):
        assert mod.join_pages(["Alpha"]) == "Alpha\n"

    def test_should_label_every_page_when_there_are_several(self, mod):
        assert mod.join_pages(["Alpha", "Beta"]) == (
            "<!-- page 1 -->\n\nAlpha\n\n<!-- page 2 -->\n\nBeta\n"
        )


class TestParseDocument:
    def test_should_parse_each_page_on_its_own_in_single_page_profile_by_default(self, mod, tmp_path):
        pages = [tmp_path / "page_0001.png", tmp_path / "page_0002.png"]
        engine = FakeEngine(["<|det|>text [1,1,2,2]<|/det|>Alpha\n", "<|det|>text [1,1,2,2]<|/det|>Beta\n"])

        result = mod.parse_document(engine, pages, one_shot=False, raw=False)

        assert engine.calls == [([pages[0]], mod.SINGLE_PAGE), ([pages[1]], mod.SINGLE_PAGE)]
        assert result == "<!-- page 1 -->\n\nAlpha\n\n<!-- page 2 -->\n\nBeta\n"

    def test_should_send_all_pages_in_one_call_in_multi_page_profile_when_one_shot(self, mod, tmp_path):
        pages = [tmp_path / "page_0001.png", tmp_path / "page_0002.png"]
        engine = FakeEngine(["<PAGE>\n<|det|>text [1,1,2,2]<|/det|>Alpha\n<PAGE>\n<|det|>text [1,1,2,2]<|/det|>Beta\n"])

        result = mod.parse_document(engine, pages, one_shot=True, raw=False)

        assert engine.calls == [(pages, mod.MULTI_PAGE)]
        assert result == "<!-- page 1 -->\n\nAlpha\n\n<!-- page 2 -->\n\nBeta\n"

    def test_should_keep_detection_tags_when_raw(self, mod, tmp_path):
        engine = FakeEngine(["<|det|>text [1,1,2,2]<|/det|>Alpha\n"])

        result = mod.parse_document(engine, [tmp_path / "scan.png"], one_shot=False, raw=True)

        assert result == "<|det|>text [1,1,2,2]<|/det|>Alpha\n"


class TestProfiles:
    def test_should_use_gundam_mode_with_the_short_window_for_single_pages(self, mod):
        assert (mod.SINGLE_PAGE.cropping, mod.SINGLE_PAGE.image_size, mod.SINGLE_PAGE.ngram_window) == (True, 640, 128)

    def test_should_use_base_mode_with_the_long_window_for_multi_page(self, mod):
        assert (mod.MULTI_PAGE.cropping, mod.MULTI_PAGE.image_size, mod.MULTI_PAGE.ngram_window) == (False, 1024, 1024)


class TestCollectPages:
    def test_should_use_an_image_as_its_own_single_page(self, mod, tmp_path):
        image = tmp_path / "scan.png"
        image.touch()

        assert mod.collect_pages(image, dpi=300, work_dir=tmp_path) == [image]

    def test_should_render_a_pdf_into_its_own_page_directory(self, mod, tmp_path, monkeypatch):
        rendered = [tmp_path / "doc" / "page_0001.png"]
        seen = {}
        monkeypatch.setattr(mod, "render_pdf", lambda pdf, dpi, out_dir: seen.update(out_dir=out_dir) or rendered)

        result = mod.collect_pages(tmp_path / "doc.pdf", dpi=300, work_dir=tmp_path)

        assert result == rendered
        assert seen["out_dir"] == tmp_path / "doc"


class TestRenderPdf:
    def test_should_render_one_png_per_page_in_page_order(self, mod, tmp_path):
        pymupdf = pytest.importorskip("pymupdf")
        pdf = tmp_path / "doc.pdf"
        with pymupdf.open() as doc:
            doc.new_page()
            doc.new_page()
            doc.save(pdf)

        pages = mod.render_pdf(pdf, dpi=36, out_dir=tmp_path / "pages")

        assert [page.name for page in pages] == ["page_0001.png", "page_0002.png"]
        assert all(page.stat().st_size > 0 for page in pages)


class TestRuntime:
    def test_should_pin_the_interpreter_and_install_the_runtime_when_provisioning(self, mod, monkeypatch, tmp_path):
        monkeypatch.setattr(mod, "VENV", tmp_path / "venv")
        commands = []
        monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kwargs: commands.append(cmd))

        mod.provision_python()

        assert commands[0][:4] == ["uv", "venv", "--python", mod.RUNTIME_PYTHON]
        assert commands[1][:3] == ["uv", "pip", "install"]
        assert any(pkg.startswith("mlx-vlm") for pkg in commands[1])
        assert "pymupdf" in commands[1]

    def test_should_refuse_to_run_off_apple_silicon(self, mod, monkeypatch):
        monkeypatch.setattr(mod.platform, "system", lambda: "Linux")
        monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")

        with pytest.raises(SystemExit, match="Apple silicon"):
            mod.ensure_apple_silicon()


class TestCli:
    def test_should_print_usage_without_touching_the_runtime(self, run_cli, tmp_path):
        result = run_cli("ocr", ["--help"], env_extra={"HOME": str(tmp_path)})

        assert result.returncode == 0
        assert "pdf" in result.stdout.lower()
        assert not (tmp_path / ".cache" / "ocr").exists()

    def test_should_fail_before_bootstrapping_when_an_input_is_missing(self, run_cli, tmp_path):
        result = run_cli("ocr", ["-i", str(tmp_path / "missing.pdf")], env_extra={"HOME": str(tmp_path)})

        assert result.returncode == 1
        assert "Input not found" in result.stderr
        assert not (tmp_path / ".cache" / "ocr").exists()

    @pytest.mark.skipif(platform.system() == "Darwin", reason="would provision the real MLX runtime")
    def test_should_refuse_to_run_on_linux(self, run_cli, tmp_path):
        image = tmp_path / "scan.png"
        image.touch()

        result = run_cli("ocr", ["-i", str(image)], env_extra={"HOME": str(tmp_path)})

        assert result.returncode == 1
        assert "Apple silicon" in result.stderr
