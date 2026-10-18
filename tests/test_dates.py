from datetime import datetime

import pytest

from probo_mcp.parsers import parse_probo_date

# Until parse_probo_date is implemented (it returns None for everything), these are expected failures.
# This switches itself off as soon as the function parses a date.
pytestmark = pytest.mark.xfail(
    parse_probo_date("14.10.2026") is None, reason="TODO: implement parse_probo_date", strict=False
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # message list (English UI month abbreviations, " - " before time)
        ("14 Oct 2026 - 18:22", datetime(2026, 10, 14, 18, 22)),
        ("01 Oct 2026 - 21:05", datetime(2026, 10, 1, 21, 5)),
        # message thread (4-letter "Sept", middle dot before time)
        ("30 Sept 2026 · 19:15", datetime(2026, 9, 30, 19, 15)),
        # document archive (Danish month abbreviations, no time)
        ("15 Okt 2026", datetime(2026, 10, 15)),
        ("13 Maj 2026", datetime(2026, 5, 13)),
        ("23 Mar 2026", datetime(2026, 3, 23)),
        # news list / dashboard (numeric)
        ("13.10.2026", datetime(2026, 10, 13)),
        ("13.10.2026 12:01", datetime(2026, 10, 13, 12, 1)),
        # news list (full Danish month name, period after the day)
        ("13. oktober 2026 12:01", datetime(2026, 10, 13, 12, 1)),
        ("9. september 2026 13:19", datetime(2026, 9, 9, 13, 19)),
        # unparseable -> None, never an exception
        ("", None),
        ("i går", None),
    ],
)
def test_parse_probo_date(text, expected):
    assert parse_probo_date(text) == expected
