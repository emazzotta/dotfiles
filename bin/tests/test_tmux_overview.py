class TestTmuxOverview:
    def should_offer_the_commands_a_person_types(self, run_cli):
        result = run_cli("tmux-overview", ["--complete"])

        assert result.stdout.split() == ["toggle", "status"]
