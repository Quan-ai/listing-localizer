from unittest.mock import patch, MagicMock
from services.scraper import scrape_product_page, is_valid_url


class TestIsValidUrl:
    def test_allows_shopee_urls(self):
        assert is_valid_url("https://shopee.co.id/product/123") is True
        assert is_valid_url("https://shopee.com.my/product/abc") is True
        assert is_valid_url("https://shopee.ph/product/xyz") is True
        assert is_valid_url("https://shopee.co.th/product/456") is True
        assert is_valid_url("https://shopee.vn/product/789") is True

    def test_allows_lazada_urls(self):
        assert is_valid_url("https://www.lazada.com.my/products/test") is True
        assert is_valid_url("https://www.lazada.co.id/products/test") is True
        assert is_valid_url("https://www.lazada.com.ph/products/test") is True
        assert is_valid_url("https://www.lazada.co.th/products/test") is True
        assert is_valid_url("https://www.lazada.vn/products/test") is True

    def test_rejects_other_domains(self):
        assert is_valid_url("https://example.com/product") is False
        assert is_valid_url("https://google.com") is False
        assert is_valid_url("not-a-url") is False

    def test_rejects_empty_string(self):
        assert is_valid_url("") is False


class TestScrapeProductPage:
    def test_extracts_title_and_description(self):
        mock_page = MagicMock()
        mock_page.title.return_value = "Test Product Title | Shopee"
        mock_page.query_selector.return_value = None

        with patch("services.scraper.sync_playwright") as mock_playwright:
            mock_browser = MagicMock()
            mock_playwright.return_value.__enter__.return_value.chromium.launch.return_value = mock_browser
            mock_browser.new_page.return_value = mock_page

            result = scrape_product_page("https://shopee.co.id/product/123")

        assert "Test Product Title" in result
