from datetime import datetime

import pytest

from probo_mcp.parsers import PROBO_TZ, parse_probo_date


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # message list (English UI month abbreviations, " - " before time)
        ("14 Oct 2026 - 18:22", datetime(2026, 10, 14, 18, 22)),
        ("01 Oct 2026 - 21:05", datetime(2026, 10, 1, 21, 5)),
        # message thread (4-letter "Sept", middle dot before time)
        ("30 Sept 2026 · 19:15", datetime(2026, 9, 30, 19, 15)),
        # message thread in the Danish UI (Danish abbreviation, middle dot)
        ("01 Okt 2026 · 21:05", datetime(2026, 10, 1, 21, 5)),
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
        # free text in message bodies ("kl." and a dot in the time), surrounding whitespace
        ("3. marts 2026 kl. 17.00", datetime(2026, 3, 3, 17, 0)),
        ("  1 May 2026  ", datetime(2026, 5, 1)),
        # unparseable -> None, never an exception
        ("", None),
        ("i går", None),
        ("31.02.2026", None),  # no such day
        ("13.10.2026 25:00", None),  # no such hour
        ("13 Ma 2026", None),  # too short to tell March from May
        ("13 Okto 2026x", None),  # trailing junk
        ("13 Foo 2026", None),
    ],
)
def test_parse_probo_date(text, expected):
    if expected is not None:
        expected = expected.replace(tzinfo=PROBO_TZ)
    assert parse_probo_date(text) == expected


def test_dates_serialise_with_an_offset():
    """Output schemas say ``format: date-time`` (RFC 3339), which needs an offset; clients enforce it."""
    winter = parse_probo_date("13.11.2026 12:01")
    summer = parse_probo_date("13.06.2026 12:01")
    assert winter is not None
    assert summer is not None
    assert winter.isoformat() == "2026-11-13T12:01:00+01:00"
    assert summer.isoformat() == "2026-06-13T12:01:00+02:00"
