from scraper.stripe_scraper import hash_content, parse_changelog


def test_hash_is_consistent():
    content = "Stripe API changelog v2024"
    assert hash_content(content) == hash_content(content)


def test_hash_changes_on_different_content():
    assert hash_content("version 1") != hash_content("version 2")


def test_hash_is_64_chars():
    result = hash_content("any content")
    assert len(result) == 64


def test_parse_changelog_removes_nav():
    html = """
    <html><body>
    <nav>Navigation links here</nav>
    <main>
        <h1>API Changelog</h1>
        <p>Version 2024-11-01: PaymentIntent now requires automatic_payment_methods</p>
    </main>
    <footer>Footer content</footer>
    </body></html>
    """
    result = parse_changelog(html)
    assert "PaymentIntent" in result
    assert "Navigation links" not in result
    assert "Footer content" not in result


def test_parse_changelog_returns_string():
    html = "<html><body><main><p>content</p></main></body></html>"
    result = parse_changelog(html)
    assert isinstance(result, str)
    assert len(result) > 0