from bs4 import BeautifulSoup

from scraper.base import BaseAPIScraper


class SlackScraper(BaseAPIScraper):

    @property
    def api_name(self) -> str:
        return "slack"

    @property
    def changelog_url(self) -> str:
        return "https://api.slack.com/changelog"

    def parse_changelog(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        main = soup.find("main") or soup.find("body")
        return main.get_text(separator="\n", strip=True) if main else soup.get_text()


async def check_slack_changelog() -> dict | None:
    scraper = SlackScraper()
    return await scraper.check_changelog()
