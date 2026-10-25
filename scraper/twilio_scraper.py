from bs4 import BeautifulSoup

from scraper.base import BaseAPIScraper


class TwilioScraper(BaseAPIScraper):

    @property
    def api_name(self) -> str:
        return "twilio"

    @property
    def changelog_url(self) -> str:
        return "https://www.twilio.com/en-us/changelog"

    def parse_changelog(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        main = soup.find("main") or soup.find("body")
        return main.get_text(separator="\n", strip=True) if main else soup.get_text()


async def check_twilio_changelog() -> dict | None:
    scraper = TwilioScraper()
    return await scraper.check_changelog()
