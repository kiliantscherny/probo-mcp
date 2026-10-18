import pytest

from probo_mcp import __main__ as cli
from probo_mcp import __version__


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"probo-mcp {__version__}"


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        ([], (("stdio",), {})),
        (
            ["--transport", "streamable-http", "--port", "9000"],
            (("streamable-http",), {"host": "127.0.0.1", "port": 9000}),
        ),
    ],
)
def test_transports(monkeypatch: pytest.MonkeyPatch, argv: list[str], expected: tuple) -> None:
    from probo_mcp import server

    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    cli.main(argv)
    assert calls == [expected]
