import json

from typer.testing import CliRunner

from growth_model_cli.main import app

runner = CliRunner()


def test_local_workflow(tmp_path):
    csv = tmp_path / "a.csv"
    assert runner.invoke(app, ["demo-data", str(csv), "--days", "70", "--new-users-per-day", "15"]).exit_code == 0

    res = runner.invoke(app, ["fit", str(csv)])
    assert res.exit_code == 0, res.output
    fit = json.loads(res.output)
    assert fit["unexpected_transitions"] == 0 and 0 < fit["rates"]["curr"] < 1

    res = runner.invoke(app, ["simulate", str(csv), "--horizon", "60", "--set", "CURR=0.95"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)[-1]["dau_vs_baseline"] > 0

    res = runner.invoke(app, ["levers", str(csv), "--horizon", "180", "--table"])
    assert res.exit_code == 0 and "curr" in res.output

    assert runner.invoke(app, ["simulate", str(csv), "--set", "nope=1"]).exit_code != 0
