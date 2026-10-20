import json

from reports.cli import main


def test_prints_report(capsys) -> None:
    def opener(url: str, timeout: float) -> bytes:
        return json.dumps({"id": 7}).encode()

    main(["7"], opener=opener)
    assert json.loads(capsys.readouterr().out) == {"id": 7}
