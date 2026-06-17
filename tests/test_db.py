import json

from psycopg.types.json import Jsonb

from job_hunting_agent import db


def test_postgres_json_parameters_use_jsonb_adapter(monkeypatch) -> None:
    monkeypatch.setattr(db, "IS_POSTGRES", True)

    params = db._params((json.dumps({"profile": {"name": "Mriganka"}}), "plain-value"))

    assert isinstance(params[0], Jsonb)
    assert params[1] == "plain-value"
