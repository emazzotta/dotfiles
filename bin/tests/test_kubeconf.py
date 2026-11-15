import pytest


@pytest.fixture
def kubeconf(run_bash, tmp_path):
    kube_dir = tmp_path / "kube"
    kube_dir.mkdir()

    def _run(*args):
        return run_bash("kubeconf", list(args), env_extra={"KUBE_DIR": str(kube_dir)})
    _run.kube_dir = kube_dir
    return _run


class TestKubeconf:
    def should_copy_the_named_kubeconfig_into_place(self, kubeconf):
        (kubeconf.kube_dir / "prod-kubeconfig.yaml").write_text("prod\n")

        result = kubeconf("prod")

        assert "Switched context to prod" in result.stdout
        assert (kubeconf.kube_dir / "config").read_text() == "prod\n"

    def should_print_the_failure_message_for_a_kubeconfig_that_does_not_exist(self, kubeconf):
        result = kubeconf("prod")

        assert "Failed to switch context to prod" in result.stdout
        assert "command not found" not in result.stderr

    def should_show_usage_without_a_provider_name(self, kubeconf):
        result = kubeconf()

        assert "usage: kubeconf" in result.stdout
