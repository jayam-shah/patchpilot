from scraper.stripe_scraper import StripeScraper


def test_hash_is_consistent():
    scraper = StripeScraper()
    content = "Stripe API changelog v2024"
    assert scraper.hash_content(content) == scraper.hash_content(content)


def test_hash_changes_on_different_content():
    scraper = StripeScraper()
    assert scraper.hash_content("version 1") != scraper.hash_content("version 2")


def test_hash_is_64_chars():
    scraper = StripeScraper()
    result = scraper.hash_content("any content")
    assert len(result) == 64


def test_parse_changelog_removes_nav():
    scraper = StripeScraper()
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
    result = scraper.parse_changelog(html)
    assert "PaymentIntent" in result
    assert "Navigation links" not in result
    assert "Footer content" not in result


def test_parse_changelog_returns_string():
    scraper = StripeScraper()
    html = "<html><body><main><p>content</p></main></body></html>"
    result = scraper.parse_changelog(html)
    assert isinstance(result, str)
    assert len(result) > 0
