# ShopeeFood Scraper

Scrape great deals from ShopeeFood using minimal browser, capturing network requests, no element selectors.

Some restaurants have special deals with 1 VND for certain menu items, this scraper helps you find them easily.

## Features

Simply provide a ShopeeFood search query URL, the scraper will fetch all related restaurants, then find great deals.

By default it will only print out deals with less than 100 VND.

## Usage

Go to https://shopeefood.vn and navigate to the desired location and search for the query. Copy the URL from your browser's address bar.

Example: District 1, Ho Chi Minh City with `highlands` query will produce an URL: `https://shopeefood.vn/ho-chi-minh/food/danh-sach-dia-diem-tai-khu-vuc-quan-1-giao-tan-noi?q=highlands`

```bash
# without Docker
python src/shopeefood_scraper.py "https://shopeefood.vn/ho-chi-minh/food/danh-sach-dia-diem-tai-khu-vuc-quan-1-giao-tan-noi?q=highlands"

# with Docker
docker build --rm -t sfc .
docker run --rm -e -it sfc python shopeefood_scraper.py "https://shopeefood.vn/ho-chi-minh/food/danh-sach-dia-diem-tai-khu-vuc-quan-1-giao-tan-noi?q=highlands"
```