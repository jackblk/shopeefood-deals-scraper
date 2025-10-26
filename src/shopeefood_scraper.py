import argparse
import asyncio
import base64
import json
import logging
import os
from typing import Callable, Optional

import zendriver
from zendriver import cdp
from zendriver.core.connection import ProtocolException

TIMEOUT = int(os.getenv("TIMEOUT", 10))  # Default timeout for requests in seconds
MAX_CONCURRENT_TABS = int(
    os.getenv("MAX_CONCURRENT_TABS", 3)
)  # Max concurrent tabs to open
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


# ---- filter funcs ----
def filter_delivery_dishes(event: cdp.network.ResponseReceived) -> bool:
    """Default filter: catch ShopeeFood dish list API"""
    return "/api/dish/get_delivery_dishes" in event.response.url


def filter_restaurant_info(event: cdp.network.ResponseReceived) -> bool:
    """Catch ShopeeFood restaurant info API"""
    if "/api/delivery/get_infos" not in event.response.url:
        return False
    headers = event.response.headers
    return "application/json" in headers.get("content-type", "")


class ShopeeFoodScraper:
    """Manages a single browser instance and multiple concurrent tabs."""

    def __init__(
        self, timeout: int = TIMEOUT, max_concurrent_tabs: int = MAX_CONCURRENT_TABS
    ):
        self.logger = logging.getLogger(__name__)
        self.timeout = timeout
        self.browser: Optional[zendriver.Browser] = None
        self.semaphore = asyncio.Semaphore(max_concurrent_tabs)

    async def start(self):
        """Start the browser."""
        if not self.browser:
            self.browser = await zendriver.start(
                headless=False,
                browser_args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-dev-shm-usage",
                ],
            )
        return self.browser

    async def stop(self):
        """Stop the browser."""
        if self.browser:
            await self.browser.stop()
            self.browser = None

    def _check_browser(self):
        if not self.browser:
            raise RuntimeError("Browser not started. Call start() first.")

    async def _catch_request_core(self, page_url: str, filter_func: Callable) -> str:
        """Core logic for a single request attempt. Ensures tab is closed."""
        self._check_browser()
        # already _check_browser so ignore pyright false positive
        tab = await self.browser.get("about:blank", new_tab=True)  # type: ignore
        if tab is None:
            raise RuntimeError("No tab found")
        await tab.send(cdp.network.enable())

        done = asyncio.Event()
        result = {}

        async def receive_handler(event: cdp.network.ResponseReceived):
            if not filter_func(event):
                return
            try:
                body, isbase64 = await tab.send(
                    cdp.network.get_response_body(event.request_id)
                )
            except ProtocolException as e:
                if (
                    e.args
                    and isinstance(e.args[0], dict)
                    and e.args[0].get("code") == -32000
                ):
                    return  # harmless race
                raise e

            if isbase64:
                body = base64.b64decode(body).decode("utf-8", errors="replace")

            result["url"] = event.response.url
            result["data"] = body
            done.set()

        tab.add_handler(cdp.network.ResponseReceived, receive_handler)
        await asyncio.sleep(0.5)  # let handler register
        await tab.get(page_url)

        try:
            await asyncio.wait_for(done.wait(), timeout=self.timeout)
        finally:
            await tab.close()
        self.logger.info(f"Captured response from {result.get('url')}")
        return result.get("data", "")

    async def catch_request(
        self,
        page_url: str,
        filter_func: Callable,
        retries: int = 2,
        backoff: float = 1.0,
    ) -> str:
        """Wrap core request with retries and semaphore control."""
        self._check_browser()

        attempt = 0
        while attempt <= retries:
            attempt += 1
            async with self.semaphore:
                try:
                    return await self._catch_request_core(page_url, filter_func)
                except asyncio.TimeoutError:
                    self.logger.warning(
                        f"Timeout on attempt {attempt}/{retries} for {page_url}"
                    )
                    if attempt <= retries:
                        delay = backoff * (2 ** (attempt - 1))
                        self.logger.info(f"Retrying in {delay:.1f}s...")
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(f"All retries failed for {page_url}")
                        return ""
        return ""

    @staticmethod
    def batch_parse_special_discounts_from_menu_infos(
        menu_infos: dict[str, dict], price_threshold=100
    ) -> dict[str, list[dict]]:
        """Parse restaurant menu infos for great deals without duplicates."""

        special_deals = {}
        for url_, menu in menu_infos.items():
            seen = set()
            good_deals = []
            for dish_type in menu:
                for item in dish_type.get("dishes", []):
                    discount_price = item.get("discount_price", {}).get("value")
                    if discount_price is None or discount_price >= price_threshold:
                        continue

                    key = (
                        item.get("name"),
                        item.get("price", {}).get("value"),
                        discount_price,
                    )

                    if key not in seen:
                        seen.add(key)
                        good_deals.append(
                            {
                                "name": item.get("name"),
                                "original_price": item.get("price", {}).get("value"),
                                "discount_price": discount_price,
                            }
                        )
            if good_deals:
                special_deals[url_] = good_deals
        return special_deals

    @staticmethod
    def extract_restaurant_urls(restaurant_items: dict):
        """Extract restaurant URLs from the search result JSON."""
        return [res["url"] for res in restaurant_items["reply"]["delivery_infos"]]

    async def get_restaurant_links_from_search(self, search_url: str) -> list[str]:
        """Get restaurant links from a search URL."""
        self._check_browser()
        restaurant_items = await self.catch_request(
            search_url,
            filter_restaurant_info,
        )
        if not restaurant_items:
            self.logger.info("No restaurant data found.")
            return []
        restaurant_urls = self.extract_restaurant_urls(json.loads(restaurant_items))
        self.logger.info(f"Found restaurants in {search_url}: {restaurant_urls}")
        return restaurant_urls

    async def batch_get_restaurant_menu_infos(
        self, restaurant_urls: list[str], max_concurrent: int = MAX_CONCURRENT_TABS
    ) -> dict[str, dict]:
        """Get menu info from a list of restaurant URLs."""
        self._check_browser()

        # Limit concurrent tabs
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_catch(url):
            async with semaphore:
                return await self.catch_request(url, filter_delivery_dishes)

        tasks = [limited_catch(url) for url in restaurant_urls]
        results = await asyncio.gather(*tasks)

        menu_infos = {}
        for url, restaurant_data in zip(restaurant_urls, results):
            if not restaurant_data:
                continue

            menu_ = json.loads(restaurant_data).get("reply", {}).get("menu_infos", {})
            if menu_:
                menu_infos[url] = menu_
        return menu_infos


async def main(init_url: str):
    if not init_url:
        raise ValueError("init_url argument is required.")

    scraper = ShopeeFoodScraper()
    await scraper.start()
    restaurant_urls = await scraper.get_restaurant_links_from_search(init_url)
    menu_infos = await scraper.batch_get_restaurant_menu_infos(restaurant_urls)
    await scraper.stop()

    special_deals = scraper.batch_parse_special_discounts_from_menu_infos(menu_infos)
    if special_deals:
        scraper.logger.info(json.dumps(special_deals, indent=2, ensure_ascii=False))
    return special_deals


if __name__ == "__main__":
    import time

    parser = argparse.ArgumentParser(description="ShopeeFood scraper")
    parser.add_argument(
        "init_url", type=str, help="Initial ShopeeFood search URL to scrape"
    )
    args = parser.parse_args()

    start = time.perf_counter()
    asyncio.run(main(args.init_url))
    end = time.perf_counter()
    print(f"\n⏱️  Finished in {end - start:.2f} seconds")
