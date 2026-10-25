import pytest
from scanner.repo_scanner import parse_repo_url, search_file_for_patterns


def test_parse_repo_url_standard():
    owner, repo = parse_repo_url("https://github.com/jayam-shah/patchpilot")
    assert owner == "jayam-shah"
    assert repo == "patchpilot"


def test_parse_repo_url_trailing_slash():
    owner, repo = parse_repo_url("https://github.com/jayam-shah/patchpilot/")
    assert owner == "jayam-shah"
    assert repo == "patchpilot"


def test_parse_repo_url_invalid():
    with pytest.raises(ValueError):
        parse_repo_url("not-a-url")


def test_search_finds_pattern():
    code = """
import stripe
intent = stripe.PaymentIntent.create(amount=1000, currency='usd')
"""
    matches = search_file_for_patterns(code, ["stripe.PaymentIntent.create"])
    assert "stripe.PaymentIntent.create" in matches


def test_search_finds_multiple_patterns():
    code = """
stripe.PaymentIntent.create(amount=100)
stripe.Customer.create(email='test@example.com')
"""
    matches = search_file_for_patterns(
        code,
        ["stripe.PaymentIntent.create", "stripe.Customer.create"],
    )
    assert len(matches) == 2


def test_search_no_match():
    code = "import flask\napp = Flask(__name__)"
    matches = search_file_for_patterns(code, ["stripe.PaymentIntent.create"])
    assert matches == []


def test_search_empty_code():
    matches = search_file_for_patterns("", ["stripe.PaymentIntent.create"])
    assert matches == []
