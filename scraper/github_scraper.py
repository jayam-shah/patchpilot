from bs4 import BeautifulSoup

from scraper.base import BaseAPIScraper


class GitHubScraper(BaseAPIScraper):

    @property
    def api_name(self) -> str:
        return "github"

    @property
    def changelog_url(self) -> str:
        return "https://developer.github.com/changes/"

    def parse_changelog(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        main = soup.find("main") or soup.find("body")
        return main.get_text(separator="\n", strip=True) if main else soup.get_text()


async def check_github_changelog() -> dict | None:
    scraper = GitHubScraper()
    return await scraper.check_changelog()
