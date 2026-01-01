import logging
from pathlib import Path

import uvicorn
from litestar import Litestar, Request, get, post
from litestar.static_files import StaticFilesConfig
from litestar.status_codes import HTTP_200_OK

from shopeefood_scraper import ShopeeFoodScraper

logger = logging.getLogger(__name__)
scraper: ShopeeFoodScraper | None = None

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def is_no_cache(request: Request) -> bool:
    return request.headers.get("Cache-Control", "") == "no-cache"


@get("/health")
async def health() -> dict:
    return {"status": "ok"}


@get("/init")
async def init_browser() -> dict:
    """Start the browser manually (optional)."""
    global scraper
    if scraper is None:
        scraper = ShopeeFoodScraper()
        await scraper.start()
        return {"ok": True, "message": "Browser started"}
    return {"ok": True, "message": "Already running"}


@get("/close")
async def close_browser() -> dict:
    """Stop browser manually."""
    global scraper
    if scraper is not None:
        await scraper.stop()
        scraper = None
        return {"ok": True, "message": "Browser stopped"}
    return {"ok": False, "message": "Browser not running"}


@get("/restaurants")
async def get_restaurants(request: Request) -> dict:
    global scraper
    if scraper is None:
        scraper = ShopeeFoodScraper()
        await scraper.start()

    url = request.query_params.get("url")
    if not url:
        return {"error": "Missing 'url'"}

    try:
        restaurant_info = await scraper.get_restaurant_info_from_search(
            url, NO_CACHE=is_no_cache(request)
        )
        return {"ok": True, "restaurants": restaurant_info}
    except Exception as e:
        logger.exception("Failed to get restaurants")
        return {"ok": False, "error": str(e)}


@post("/deals", status_code=HTTP_200_OK)
async def get_deals(request: Request) -> dict:
    """Fetch restaurant menu info for a list of URLs."""
    global scraper
    if scraper is None:
        scraper = ShopeeFoodScraper()
        await scraper.start()

    data = await request.json()
    urls = data.get("urls")
    if not urls:
        return {"error": "Missing 'urls'"}

    try:
        menu_infos = await scraper.batch_get_restaurant_menu_infos(
            urls, NO_CACHE=is_no_cache(request)
        )
        deals = scraper.batch_parse_special_discounts_from_menu_infos(menu_infos)
        return {"ok": True, "deals": deals}
    except Exception as e:
        logger.exception("Failed to fetch menus")
        return {"ok": False, "error": str(e)}


app = Litestar(
    route_handlers=[health, init_browser, close_browser, get_restaurants, get_deals],
    static_files_config=[
        StaticFilesConfig(path="/", directories=[STATIC_DIR], html_mode=True)
    ],
)
if __name__ == "__main__":
    import os

    PORT = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
