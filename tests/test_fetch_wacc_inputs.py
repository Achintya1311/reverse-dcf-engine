"""P71: the WACC refresh script must not fetch or write anything on --help."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_wacc_inputs  # noqa: E402


def _no_network(*args, **kwargs):
    raise AssertionError("fetch_wacc_inputs touched the network")


def test_help_exits_without_fetching(monkeypatch, capsys):
    monkeypatch.setattr(fetch_wacc_inputs.requests, "get", _no_network)
    with pytest.raises(SystemExit) as exc:
        fetch_wacc_inputs.main(["--help"])
    assert exc.value.code == 0
    assert "--out-dir" in capsys.readouterr().out


def test_out_dir_redirects_every_fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch_wacc_inputs, "verify_industry_classification", lambda: fetch_wacc_inputs.INDUSTRY)
    for name in ("fetch_india_erp", "fetch_industry_beta", "fetch_risk_free_rate"):
        monkeypatch.setattr(fetch_wacc_inputs, name, lambda fetched_date, _n=name: pd.DataFrame([{"source": _n}]))
    fetch_wacc_inputs.main(["--out-dir", str(tmp_path)])
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "india_10y_gsec_yield.csv",
        "india_country_risk_premium.csv",
        "india_industry_beta.csv",
    ]
