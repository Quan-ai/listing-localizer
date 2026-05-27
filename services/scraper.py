from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


ALLOWED_DOMAINS = {
    "shopee.co.id", "shopee.com.my", "shopee.ph", "shopee.co.th", "shopee.vn",
    "shopee.sg", "shopee.tw", "shopee.com.br", "shopee.pl", "shopee.cl",
    "shopee.com.co", "shopee.co", "shopee.fr", "shopee.es", "shopee.co.kr",
    "shopee.co.jp", "shopee.com.mx",
    "lazada.com.my", "lazada.co.id", "lazada.com.ph", "lazada.co.th",
    "lazada.vn", "lazada.sg",
    "www.lazada.com.my", "www.lazada.co.id", "www.lazada.com.ph",
    "www.lazada.co.th", "www.lazada.vn", "www.lazada.sg",
}


def is_valid_url(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        parsed = urlparse(url)
        return parsed.hostname in ALLOWED_DOMAINS
    except Exception:
        return False


import re


def _extract_from_shopee_url(url: str) -> str:
    """Extract product keywords from a Shopee URL slug.

    Shopee URLs embed the product name as a hyphenated slug before the
    ``-i.SHOP_ID.ITEM_ID`` suffix. This avoids the login wall that
    blocks unauthenticated scraping.
    """
    # Extract the path segment containing the product slug
    path = urlparse(url).path.strip("/")
    # Remove the "-i.SHOP_ID.ITEM_ID" suffix
    slug = re.sub(r"-i\.\d+\.\d+$", "", path)
    if not slug:
        raise ValueError("Could not extract product name from URL. Please use Text or Screenshot input.")
    # Convert slug to readable text: "1000ml-304-Stainless-Steel..." → "1000ml 304 Stainless Steel..."
    readable = slug.replace("-", " ")
    return f"Product Name: {readable}\n\n(Extracted from URL. For best results, provide a full description via Text input.)"


def scrape_product_page(url: str) -> str:
    if not is_valid_url(url):
        raise ValueError(f"URL not allowed: {url}")

    parsed = urlparse(url)
    is_shopee = "shopee" in parsed.hostname

    # Shopee blocks unauthenticated scraping — extract keywords from URL instead
    if is_shopee:
        return _extract_from_shopee_url(url)

    # Lazada: scrape normally
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
            )
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {} };
            """)
            page.set_extra_http_headers({
                "Accept-Language": "en-US,en;q=0.9,ms;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            })
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            title = page.title()
            parts = [f"Product Title: {title}"]

            body = page.query_selector("body")
            if body:
                full_text = body.inner_text()
                parts.append(f"Page Content: {full_text[:5000]}")

            return "\n\n".join(parts)
        except Exception as e:
            raise RuntimeError(f"Failed to scrape {url}: {str(e)}") from e
        finally:
            browser.close()
