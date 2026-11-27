import pytest

from probo_mcp import __main__ as cli
from probo_mcp import __version__


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"probo-mcp {__version__}"


def test_stdio_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from probo_mcp import server

    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append(a))
    cli.main([])
    assert calls == [("stdio",)]


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, str | None]]:
    """Calls to `_serve_http` as (host, port, token), instead of starting a server."""
    calls: list[tuple[str, int, str | None]] = []
    monkeypatch.setattr(cli, "_serve_http", lambda host, port, token: calls.append((host, port, token)))
    monkeypatch.delenv("PROBO_HTTP_TOKEN", raising=False)
    return calls


def test_http_on_loopback_needs_no_token(served: list) -> None:
    cli.main(["--transport", "streamable-http", "--port", "9000"])
    cli.main(["--transport", "streamable-http", "--host", "::1"])
    assert served == [("127.0.0.1", 9000, None), ("::1", 8000, None)]


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
def test_http_refuses_non_loopback_hosts(host: str, served: list) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--transport", "streamable-http", "--host", host])
    assert exit_info.value.code == 2
    assert served == []


def test_remote_http_gets_a_random_token(served: list, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--allow-remote"])
    cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--allow-remote"])
    (_, _, first), (_, _, second) = served
    assert first
    assert second != first
    err = capsys.readouterr().err
    assert f"Authorization: Bearer {first}" in err
    assert "not encrypted" in err


def test_http_token_from_the_environment(served: list, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROBO_HTTP_TOKEN", "t" * 40)
    cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--allow-remote"])
    cli.main(["--transport", "streamable-http"])  # also enforced on loopback when set
    assert [token for _, _, token in served] == ["t" * 40, "t" * 40]


def test_short_http_tokens_are_refused(served: list, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROBO_HTTP_TOKEN", "hunter2")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--transport", "streamable-http", "--host", "0.0.0.0", "--allow-remote"])
    assert exit_info.value.code == 2
    assert served == []
