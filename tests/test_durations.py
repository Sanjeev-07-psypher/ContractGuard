import pytest

from contractguard.extraction.durations import find_durations, parse_duration, words_to_number


@pytest.mark.parametrize(
    "text, value, unit, days",
    [
        ("thirty (30) days", 30, "day", 30),
        ("30 days", 30, "day", 30),
        ("thirty days", 30, "day", 30),
        ("one (1) month", 1, "month", 30),
        ("2 weeks", 2, "week", 14),
        ("ninety calendar days", 90, "day", 90),
        ("15 business days", 15, "day", 21),
        ("thirty (30) working days", 30, "day", 42),
        ("1 year", 1, "year", 365),
        ("three (3) years", 3, "year", 1095),
        ("Net 30", 30, "day", 30),
        ("net 45", 45, "day", 45),
        ("forty-five (45) days", 45, "day", 45),
        ("one hundred and twenty days", 120, "day", 120),
        ("(30) days", 30, "day", 30),
        ("seven (7) days' prior written notice", 7, "day", 7),
        ("Thirty (30) Days", 30, "day", 30),
    ],
)
def test_parse_duration(text, value, unit, days):
    d = parse_duration(text)
    assert d is not None
    assert (d.value, d.unit, d.days) == (value, unit, days)


def test_digit_wins_over_word():
    assert parse_duration("thirty (45) days").value == 45


@pytest.mark.parametrize(
    "text", ["fifth (5th) day of each month", "1% per month", "per month", "Clause 30", ""]
)
def test_non_durations(text):
    assert find_durations(text) == []


def test_find_all_keeps_order_and_exact_text():
    text = "within fifteen (15) days, or Net 30, or 2 weeks"
    found = find_durations(text)
    assert [d.days for d in found] == [15, 30, 14]
    assert all(text[d.start : d.end] == d.text for d in found)


@pytest.mark.parametrize(
    "words, n",
    [("forty-five", 45), ("one hundred and twenty", 120), ("nine hundred ninety nine", 999),
     ("twelve", 12), ("banana", None)],
)  # fmt: skip
def test_words_to_number(words, n):
    assert words_to_number(words) == n
