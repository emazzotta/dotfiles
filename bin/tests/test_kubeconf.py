import os
import re
import subprocess

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

FUNCTIONS = BIN_DIR.parent / "bash" / ".bashrc.d" / "20-functions.sh"
KC_DEFINITION = re.compile(r"^(?:function kc|kc\(\)) \{\n.*?^\}\n", re.MULTILINE | re.DOTALL)
SHELLS = {"bash": ["bash"], "zsh": ["zsh", "-f"]}
ORIGINAL_CONFIG = "/original/personal-infra.yaml"


@pytest.fixture
def kube_dir(tmp_path):
    directory = tmp_path / "kube"
    directory.mkdir()
    return directory


@pytest.fixture
def kubeconf(run_bash, kube_dir):
    def _run(*args):
        return run_bash("kubeconf", list(args), env_extra={"KUBE_DIR": str(kube_dir)})
    return _run


class TestKubeconf:
    def should_print_the_path_of_the_named_kubeconfig(self, kubeconf, kube_dir):
        (kube_dir / "prod-kubeconfig.yaml").write_text("prod\n")

        result = kubeconf("prod")

        assert result.returncode == 0
        assert result.stdout == f"{kube_dir}/prod-kubeconfig.yaml\n"

    def should_not_copy_the_kubeconfig_into_place(self, kubeconf, kube_dir):
        (kube_dir / "prod-kubeconfig.yaml").write_text("prod\n")

        kubeconf("prod")

        assert not (kube_dir / "config").exists()

    def should_fail_on_stderr_for_a_kubeconfig_that_does_not_exist(self, kubeconf):
        result = kubeconf("prod")

        assert result.returncode == 1
        assert result.stdout == ""
        assert "prod-kubeconfig.yaml" in result.stderr

    def should_show_usage_on_stderr_without_a_provider_name(self, kubeconf):
        result = kubeconf()

        assert result.returncode == 1
        assert result.stdout == ""
        assert "usage: kubeconf" in result.stderr

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage_on_stdout_for_the_help_flags(self, kubeconf, flag):
        result = kubeconf(flag)

        assert result.returncode == 0
        assert "usage: kubeconf" in result.stdout
        assert result.stderr == ""


@pytest.fixture(params=["bash", pytest.param("zsh", marks=requires_tool("zsh"))])
def kc(request, tmp_path, kube_dir):
    definition = KC_DEFINITION.search(FUNCTIONS.read_text())
    assert definition, "kc is not defined in 20-functions.sh"
    sourced = tmp_path / "kc-definition.sh"
    sourced.write_text(definition.group(0))

    def _kc(*args):
        script = (f'source "{sourced}"; kc "$@"; rc=$?; '
                  'echo "exported=$(printenv KUBECONFIG)"; exit $rc')
        env = {**os.environ, "PATH": f"{BIN_DIR}:{os.environ['PATH']}", "KUBE_DIR": str(kube_dir),
               "KUBECONFIG": ORIGINAL_CONFIG}
        return subprocess.run([*SHELLS[request.param], "-c", script, "kc", *args],
                              capture_output=True, text=True, env=env, cwd=tmp_path)
    return _kc


class TestKc:
    def should_export_the_named_kubeconfig_in_the_current_shell(self, kc, kube_dir):
        (kube_dir / "prod-kubeconfig.yaml").write_text("prod\n")

        result = kc("prod")

        assert result.returncode == 0, result.stderr
        assert f"exported={kube_dir}/prod-kubeconfig.yaml" in result.stdout.splitlines()

    def should_announce_the_switch(self, kc, kube_dir):
        (kube_dir / "prod-kubeconfig.yaml").write_text("prod\n")

        result = kc("prod")

        assert "Switched context to prod" in result.stdout.splitlines()

    def should_leave_the_kubeconfig_alone_when_the_name_is_unknown(self, kc):
        result = kc("prod")

        assert result.returncode != 0
        assert f"exported={ORIGINAL_CONFIG}" in result.stdout.splitlines()
        assert "Switched context" not in result.stdout
        assert "prod-kubeconfig.yaml" in result.stderr

    def should_leave_the_kubeconfig_alone_without_a_name(self, kc):
        result = kc()

        assert result.returncode != 0
        assert f"exported={ORIGINAL_CONFIG}" in result.stdout.splitlines()
        assert "usage: kubeconf" in result.stderr

    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage_without_switching_for_the_help_flags(self, kc, flag):
        result = kc(flag)

        assert result.returncode == 0, result.stderr
        assert "usage: kubeconf" in result.stdout
        assert f"exported={ORIGINAL_CONFIG}" in result.stdout.splitlines()
        assert "Switched context" not in result.stdout
