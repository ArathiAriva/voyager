import logging
import httpx
from html.parser import HTMLParser

logger = logging.getLogger("voyager.utils")


async def fetch_og_metadata(url: str) -> tuple[str | None, str | None]:
    """Fetch Open Graph title and image from a URL. Returns (title, thumbnail_url)."""
    try:
        class OGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.og_title: str | None = None
                self.og_image: str | None = None
                self.page_title: str | None = None
                self._in_title = False

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                if tag == "meta":
                    prop = attrs_dict.get("property", "")
                    if prop == "og:title":
                        self.og_title = attrs_dict.get("content")
                    elif prop == "og:image":
                        self.og_image = attrs_dict.get("content")
                elif tag == "title":
                    self._in_title = True

            def handle_data(self, data):
                if self._in_title and not self.page_title:
                    self.page_title = data.strip()

            def handle_endtag(self, tag):
                if tag == "title":
                    self._in_title = False

        async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
            resp = await client.get(url, headers={"User-Agent": "Voyager/1.0 (link preview)"})
            resp.raise_for_status()
            if "text/html" not in resp.headers.get("content-type", ""):
                return None, None
            parser = OGParser()
            parser.feed(resp.text[:50_000])
            title = parser.og_title or parser.page_title
            return title, parser.og_image
    except Exception as e:
        logger.warning("OG fetch failed for %s: %s", url, e)
        return None, None
