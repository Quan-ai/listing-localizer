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


def scrape_product_page(url: str) -> str:
    if not is_valid_url(url):
        raise ValueError(f"URL not allowed: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

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
