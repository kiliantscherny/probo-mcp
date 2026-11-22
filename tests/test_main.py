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


def test_fetch_history_runs_until_done(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from probo_mcp import archive, service
    from probo_mcp.models import HistoryEntry, HistoryResult

    batches = [
        HistoryResult(
            saved=[HistoryEntry(kind="news", id="a", title="Old post", saved_to="/x")], archive_dir="/x", remaining=1
        ),
        HistoryResult(
            saved=[HistoryEntry(kind="document", id="b", title="Minutes.pdf", saved_to="/y")],
            archive_dir="/x",
            remaining=0,
        ),
    ]
    sections_seen = []

    async def fake_fetch_history(svc, *, sections, max_items):
        sections_seen.append(tuple(sections))
        return batches.pop(0)

    class FakeService:
        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(archive, "fetch_history", fake_fetch_history)
    monkeypatch.setattr(service.ProboService, "from_settings", classmethod(lambda cls, s: FakeService()))
    monkeypatch.setattr("probo_mcp.config.Settings.from_env", classmethod(lambda cls: object()))
    cli.main(["--fetch-history"])
    out = capsys.readouterr()
    assert "Old post" in out.out
    assert "Minutes.pdf" in out.out
    assert "Done: 0 left" in out.err
    assert sections_seen == [("news", "document"), ("news", "document")]


def test_set_password_needs_a_real_terminal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(""))  # e.g. run by an agent, with no terminal
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--set-password"])
    assert exit_info.value.code == 2
    assert "your own terminal" in capsys.readouterr().err


def test_set_password_saves_for_the_configured_site(monkeypatch: pytest.MonkeyPatch) -> None:
    from probo_mcp import credentials

    saved = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.setenv("PROBO_BASE_URL", "example.probo.dk")
    monkeypatch.setenv("PROBO_USERNAME", "me@example.com")
    monkeypatch.setattr(credentials, "set_password", lambda base, user: saved.append((base, user)))
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--set-password"])
    assert exit_info.value.code == 0
    assert saved == [("https://example.probo.dk", "me@example.com")]


def test_set_password_refuses_other_sites(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.setenv("PROBO_BASE_URL", "https://evil.example")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--set-password"])
    assert exit_info.value.code == 2
    assert "probo.dk" in capsys.readouterr().err


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com"])
def test_http_refuses_non_loopback_hosts(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from probo_mcp import server

    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: pytest.fail("should not start"))
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--transport", "streamable-http", "--host", host])
    assert exit_info.value.code == 2


def test_http_allows_remote_hosts_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    from probo_mcp import server

    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append(kw))
    cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--allow-remote"])
    cli.main(["--transport", "streamable-http", "--host", "::1"])
    assert [c["host"] for c in calls] == ["0.0.0.0", "::1"]
