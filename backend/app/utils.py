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


def dest_matches(a: str, b: str) -> bool:
    """Loose destination match: 'Istanbul' ~ 'Istanbul, Turkey' (either direction).

    City name must match exactly (case-insensitive) -- word-substring matching
    on city alone previously caused false collisions ('Rome' ~ 'New Rome'). When
    both sides specify a region/country, that must also match, so same-named
    cities in different countries don't collide ('San Jose, Costa Rica' ~
    'San Jose, USA', 'Valencia, Spain' ~ 'Valencia, Venezuela'); when one side
    omits the region, city-only equality is enough."""
    a, b = a.lower().strip(), b.lower().strip()
    a_parts = [p.strip() for p in a.split(",", 1)]
    b_parts = [p.strip() for p in b.split(",", 1)]
    a_city, b_city = a_parts[0], b_parts[0]
    if not a_city or a_city != b_city:
        return False
    a_region = a_parts[1] if len(a_parts) > 1 else None
    b_region = b_parts[1] if len(b_parts) > 1 else None
    if a_region and b_region:
        return a_region == b_region or a_region in b_region or b_region in a_region
    return True
