# Listing Localizer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web app where sellers input product info (text/URL/screenshot) and get back localized Shopee/Lazada listings for 5 SE Asian markets.

**Architecture:** Single FastAPI server with HTMX frontend. Three input paths — text goes directly to LLM, URL triggers Playwright scrape then LLM, image triggers Vision LLM then text LLM. All LLM calls go through services/llm.py. Jinja2 templates render the UI; HTMX handles partial page updates without a JS framework.

**Tech Stack:** Python 3.12+ / FastAPI / Jinja2 / HTMX / Tailwind CSS CDN / OpenAI SDK (pointed at DeepSeek) / Playwright

---

## File Structure

```
shopee-tools/
├── main.py                  # FastAPI app, routes, startup
├── config.py                # Env var loading
├── requirements.txt         # Dependencies
├── .env.example             # Template for env vars
├── services/
│   ├── __init__.py
│   ├── llm.py               # All LLM calls (extraction, localization, vision)
│   └── scraper.py           # Playwright product page scraper
├── prompts/
│   ├── __init__.py
│   └── localization.py      # Prompt strings for extraction + 5-market localization
├── templates/
│   ├── base.html            # Layout shell (Tailwind + HTMX CDNs)
│   ├── index.html           # Main page: input form with tabs
│   └── result.html          # HTMX partial: localized listing cards
└── tests/
    ├── __init__.py
    ├── test_llm.py          # LLM service tests (mocked API)
    ├── test_scraper.py      # Scraper tests (mocked Playwright)
    └── test_routes.py       # FastAPI route tests (TestClient)
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `.env.example`
- Create: `services/__init__.py`
- Create: `prompts/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write requirements.txt**

```txt
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
jinja2>=3.1.0
python-multipart>=0.0.9
openai>=1.30.0
playwright>=1.43.0
python-dotenv>=1.0.0
itsdangerous>=2.0.0
```

- [ ] **Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 3: Write config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TEXT_MODEL = os.getenv("TEXT_MODEL", "deepseek-chat")
VISION_MODEL = os.getenv("VISION_MODEL", "deepseek-chat")

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY environment variable is required")
```

- [ ] **Step 4: Write .env.example**

```
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
TEXT_MODEL=deepseek-chat
VISION_MODEL=deepseek-chat
```

- [ ] **Step 5: Create empty __init__.py files**

```bash
echo "" > services/__init__.py
echo "" > prompts/__init__.py
echo "" > tests/__init__.py
```

- [ ] **Step 6: Verify config loads**

Run: `python -c "import config; print('DEEPSEEK_BASE_URL:', config.DEEPSEEK_BASE_URL)"`
Expected: Prints the base URL without errors (set `DEEPSEEK_API_KEY=test` first)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt config.py .env.example services/__init__.py prompts/__init__.py tests/__init__.py
git commit -m "chore: project scaffolding with config and dependencies"
```

---

### Task 2: Prompt Templates

**Files:**
- Create: `prompts/localization.py`

- [ ] **Step 1: Write prompts/localization.py**

```python
EXTRACTION_PROMPT = """You are an e-commerce product cataloging expert. Given raw product information, extract structured data.

Return a JSON object with these fields:
- "name": The product name (string)
- "category": Product category (string)
- "key_features": List of 3-5 key selling points (list of strings)
- "specs": Technical specifications or materials (string, can be empty)
- "price_hint": Price range if mentioned (string, can be empty)

Only return valid JSON. Do not wrap in markdown code blocks."""

INDONESIA_PROMPT = """You are an expert e-commerce copywriter for Shopee Indonesia and Lazada Indonesia. Given product information in JSON format, create a localized product listing in Bahasa Indonesia.

Guidelines:
- Use price-sensitive language ("hemat", "murah", "promo")
- Include "Gratis Ongkir" naturally if it fits
- Mention "halal-friendly" or "BPOM" if relevant to the product
- Indonesian consumers respond to warmth and community ("kak", "bestie")
- Keywords should include common Indonesian search terms

Return a JSON object with:
- "title": SEO-optimized title in Bahasa Indonesia (max 120 characters)
- "description": 2 paragraphs of compelling product description in Bahasa Indonesia
- "keywords": 10-15 comma-separated search keywords in Bahasa Indonesia"""

THAILAND_PROMPT = """You are an expert e-commerce copywriter for Shopee Thailand and Lazada Thailand. Given product information in JSON format, create a localized product listing in Thai.

Guidelines:
- Use friendly, conversational tone
- NEVER reference the royal family or use royal vocabulary
- Thai consumers like detailed specs and usage instructions
- Include common Thai shopping phrases ("ของแท้", "ส่งเร็ว", "รับประกัน")
- Keywords should include common Thai search terms

Return a JSON object with:
- "title": SEO-optimized title in Thai (max 120 characters)
- "description": 2 paragraphs of compelling product description in Thai
- "keywords": 10-15 comma-separated search keywords in Thai"""

VIETNAM_PROMPT = """You are an expert e-commerce copywriter for Shopee Vietnam and Lazada Vietnam. Given product information in JSON format, create a localized product listing in Vietnamese.

Guidelines:
- Use youthful, energetic language
- Casual tone like talking to a friend ("bạn", "siêu", "cực")
- Vietnamese consumers love "hot trends" and social proof
- Include common Vietnamese shopping phrases ("hàng chính hãng", "freeship", "sale to")
- Keywords should include common Vietnamese search terms

Return a JSON object with:
- "title": SEO-optimized title in Vietnamese (max 120 characters)
- "description": 2 paragraphs of compelling product description in Vietnamese
- "keywords": 10-15 comma-separated search keywords in Vietnamese"""

MALAYSIA_PROMPT = """You are an expert e-commerce copywriter for Shopee Malaysia and Lazada Malaysia. Given product information in JSON format, create a localized product listing in Bahasa Melayu with natural English mixing (Bahasa Pasar style).

Guidelines:
- Mix English and Malay naturally — this is how Malaysians shop online
- Use "boleh", "best", "power" and other Malaysian English expressions
- Mention "free shipping" / "penghantaran percuma" where relevant
- Multi-ethnic appeal: the copy should feel natural to Malay, Chinese, and Indian consumers
- Keywords should mix English and Malay terms

Return a JSON object with:
- "title": SEO-optimized title mixing English and Malay (max 120 characters)
- "description": 2 paragraphs of compelling product description in mixed English-Malay
- "keywords": 10-15 comma-separated search keywords mixing English and Malay"""

PHILIPPINES_PROMPT = """You are an expert e-commerce copywriter for Shopee Philippines and Lazada Philippines. Given product information in JSON format, create a localized product listing in Taglish (Tagalog + English).

Guidelines:
- Mix Tagalog and English naturally — this is "Taglish" and it's how Filipinos communicate
- Warm, friendly, and personal tone ("mga ka-shopping", "sis", "boss")
- Mention "free shipping", "COD available", and "sale" where relevant
- Filipinos love a good deal and respond to "sulit" (worth it), "mura" (cheap), "legit"
- Keywords should mix Tagalog and English terms

Return a JSON object with:
- "title": SEO-optimized title in Taglish (max 120 characters)
- "description": 2 paragraphs of compelling product description in Taglish
- "keywords": 10-15 comma-separated search keywords in Taglish"""

MARKET_PROMPTS = {
    "indonesia": INDONESIA_PROMPT,
    "thailand": THAILAND_PROMPT,
    "vietnam": VIETNAM_PROMPT,
    "malaysia": MALAYSIA_PROMPT,
    "philippines": PHILIPPINES_PROMPT,
}

MARKET_NAMES = {
    "indonesia": "Indonesia (Bahasa)",
    "thailand": "Thailand (Thai)",
    "vietnam": "Vietnam (Vietnamese)",
    "malaysia": "Malaysia (Malay)",
    "philippines": "Philippines (Taglish)",
}
```

- [ ] **Step 2: Verify prompt imports**

Run: `python -c "from prompts.localization import MARKET_PROMPTS, MARKET_NAMES; print(len(MARKET_PROMPTS), 'markets')"`
Expected: `5 markets`

- [ ] **Step 3: Commit**

```bash
git add prompts/localization.py
git commit -m "feat: add LLM prompt templates for 5-market localization"
```

---

### Task 3: LLM Service

**Files:**
- Create: `services/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_llm.py`:

```python
import json
from unittest.mock import patch, MagicMock
from services.llm import extract_product_info, localize_for_market, process_text_input


class TestExtractProductInfo:
    def test_extracts_structured_json(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "name": "Wireless Earbuds",
                        "category": "Electronics",
                        "key_features": ["Noise cancelling", "30hr battery"],
                        "specs": "Bluetooth 5.3",
                        "price_hint": "$25"
                    })
                )
            )
        ]

        with patch("services.llm.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_response
            result = extract_product_info("Wireless Bluetooth Earbuds with noise cancelling")

        assert result["name"] == "Wireless Earbuds"
        assert result["category"] == "Electronics"
        assert len(result["key_features"]) == 2
        assert mock_client.chat.completions.create.call_count == 1


class TestLocalizeForMarket:
    def test_localizes_for_indonesia(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "title": "Earbuds Wireless Bluetooth Hemat - Noise Cancelling",
                        "description": "Paragraf 1 tentang produk. Paragraf 2 tentang manfaat.",
                        "keywords": "earbuds, bluetooth, wireless, hemat, noise cancelling"
                    })
                )
            )
        ]

        product_info = {"name": "Wireless Earbuds", "category": "Electronics", "key_features": [], "specs": "", "price_hint": ""}

        with patch("services.llm.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_response
            result = localize_for_market(product_info, "indonesia")

        assert "title" in result
        assert "description" in result
        assert "keywords" in result
        assert mock_client.chat.completions.create.call_count == 1


class TestProcessTextInput:
    def test_returns_all_five_markets(self):
        mock_extract_response = MagicMock()
        mock_extract_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "name": "Test Product",
                        "category": "Test",
                        "key_features": ["Feature 1"],
                        "specs": "",
                        "price_hint": ""
                    })
                )
            )
        ]

        mock_localize_response = MagicMock()
        mock_localize_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "title": "Localized Title",
                        "description": "Localized description.",
                        "keywords": "kw1, kw2, kw3"
                    })
                )
            )
        ]

        with patch("services.llm.client") as mock_client:
            mock_client.chat.completions.create.side_effect = [
                mock_extract_response,
                mock_localize_response,
                mock_localize_response,
                mock_localize_response,
                mock_localize_response,
                mock_localize_response,
            ]
            result = process_text_input("Test product text")

        assert "product_info" in result
        assert "localizations" in result
        assert len(result["localizations"]) == 5
        assert "indonesia" in result["localizations"]
        assert "thailand" in result["localizations"]
        assert "vietnam" in result["localizations"]
        assert "malaysia" in result["localizations"]
        assert "philippines" in result["localizations"]

    def test_returns_error_on_llm_failure(self):
        with patch("services.llm.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            result = process_text_input("Test product text")

        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: All 4 tests FAIL (module not found: services.llm)

- [ ] **Step 3: Write services/llm.py**

Create `services/llm.py`:

```python
import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, TEXT_MODEL, VISION_MODEL
from prompts.localization import EXTRACTION_PROMPT, MARKET_PROMPTS

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

MARKET_ORDER = ["indonesia", "thailand", "vietnam", "malaysia", "philippines"]


def extract_product_info(text: str) -> dict:
    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": text[:4000]},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return json.loads(response.choices[0].message.content)


def localize_for_market(product_info: dict, market: str) -> dict:
    prompt = MARKET_PROMPTS.get(market, MARKET_PROMPTS["indonesia"])
    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(product_info, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(response.choices[0].message.content)


def extract_from_image(image_data: bytes) -> dict:
    import base64

    image_b64 = base64.b64encode(image_data).decode()
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract product information from this image.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return json.loads(response.choices[0].message.content)


def process_text_input(text: str) -> dict:
    try:
        product_info = extract_product_info(text)
    except Exception as e:
        return {"error": f"Failed to extract product info: {str(e)}"}

    results = {}
    for market in MARKET_ORDER:
        try:
            results[market] = localize_for_market(product_info, market)
        except Exception as e:
            results[market] = {"error": f"Failed for {market}: {str(e)}"}

    return {"product_info": product_info, "localizations": results}


def process_url_input(scraped_text: str) -> dict:
    return process_text_input(scraped_text)


def process_image_input(image_data: bytes) -> dict:
    try:
        product_info = extract_from_image(image_data)
    except Exception as e:
        return {"error": f"Failed to extract product info from image: {str(e)}"}

    results = {}
    for market in MARKET_ORDER:
        try:
            results[market] = localize_for_market(product_info, market)
        except Exception as e:
            results[market] = {"error": f"Failed for {market}: {str(e)}"}

    return {"product_info": product_info, "localizations": results}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add services/llm.py tests/test_llm.py
git commit -m "feat: add LLM service with extraction and 5-market localization"
```

---

### Task 4: Scraper Service

**Files:**
- Create: `services/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_scraper.py`:

```python
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
            mock_browser.new_page.return_value.__enter__.return_value = mock_page

            result = scrape_product_page("https://shopee.co.id/product/123")

        assert "Test Product Title" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scraper.py -v`
Expected: All tests FAIL (module not found)

- [ ] **Step 3: Write services/scraper.py**

Create `services/scraper.py`:

```python
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
        page = browser.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            title = page.title()
            parts = []
            parts.append(f"Product Title: {title}")

            body = page.query_selector("body")
            if body:
                full_text = body.inner_text()
                parts.append(f"Page Content: {full_text[:5000]}")

            browser.close()
            return "\n\n".join(parts)
        except Exception as e:
            browser.close()
            raise RuntimeError(f"Failed to scrape {url}: {str(e)}")
```

- [ ] **Step 4: Install Playwright browsers**

Run: `playwright install chromium`
Expected: Chromium browser downloads and installs

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scraper.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add services/scraper.py tests/test_scraper.py
git commit -m "feat: add Playwright scraper with URL validation"
```

---

### Task 5: FastAPI App, Routes, and Templates

**Files:**
- Create: `main.py`
- Create: `templates/base.html`
- Create: `templates/index.html`
- Create: `templates/result.html`
- Create: `tests/test_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/test_routes.py`:

```python
from unittest.mock import patch, MagicMock, ANY
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestHomePage:
    def test_get_home_returns_200(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "Listing Localizer" in response.text


class TestGenerateTextInput:
    @patch("main.process_text_input")
    def test_generates_from_text(self, mock_process):
        mock_process.return_value = {
            "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
            "localizations": {
                "indonesia": {"title": "Indo Title", "description": "Indo desc", "keywords": "indo, kw"},
                "thailand": {"title": "Thai Title", "description": "Thai desc", "keywords": "thai, kw"},
                "vietnam": {"title": "Viet Title", "description": "Viet desc", "keywords": "viet, kw"},
                "malaysia": {"title": "MY Title", "description": "MY desc", "keywords": "my, kw"},
                "philippines": {"title": "PH Title", "description": "PH desc", "keywords": "ph, kw"},
            },
        }

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
        })

        assert response.status_code == 200
        assert "Indo Title" in response.text
        assert "Thai Title" in response.text
        mock_process.assert_called_once_with("Test product")

    @patch("main.process_text_input")
    def test_handles_empty_text(self, mock_process):
        mock_process.return_value = {"error": "No content provided"}

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "",
            "url": "",
        })

        assert response.status_code == 200
        assert "error" in response.text.lower()


class TestGenerateUrlInput:
    @patch("main.process_url_input")
    @patch("main.scrape_product_page")
    @patch("main.is_valid_url")
    def test_generates_from_url(self, mock_valid, mock_scrape, mock_process):
        mock_valid.return_value = True
        mock_scrape.return_value = "Product Title: Test\nPage Content: Test content"
        mock_process.return_value = {
            "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
            "localizations": {
                "indonesia": {"title": "Indo Title", "description": "Indo desc", "keywords": "kw"},
                "thailand": {"title": "Thai Title", "description": "Thai desc", "keywords": "kw"},
                "vietnam": {"title": "Viet Title", "description": "Viet desc", "keywords": "kw"},
                "malaysia": {"title": "MY Title", "description": "MY desc", "keywords": "kw"},
                "philippines": {"title": "PH Title", "description": "PH desc", "keywords": "kw"},
            },
        }

        response = client.post("/generate", data={
            "input_type": "url",
            "text": "",
            "url": "https://shopee.co.id/product/123",
        })

        assert response.status_code == 200
        assert "Indo Title" in response.text

    def test_rejects_invalid_url(self):
        response = client.post("/generate", data={
            "input_type": "url",
            "text": "",
            "url": "https://example.com/product",
        })

        assert response.status_code == 200
        assert "Invalid" in response.text or "invalid" in response.text.lower()


class TestGenerateImageInput:
    @patch("main.process_image_input")
    def test_generates_from_image(self, mock_process):
        mock_process.return_value = {
            "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
            "localizations": {
                "indonesia": {"title": "Indo Title", "description": "Indo desc", "keywords": "kw"},
                "thailand": {"title": "Thai Title", "description": "Thai desc", "keywords": "kw"},
                "vietnam": {"title": "Viet Title", "description": "Viet desc", "keywords": "kw"},
                "malaysia": {"title": "MY Title", "description": "MY desc", "keywords": "kw"},
                "philippines": {"title": "PH Title", "description": "PH desc", "keywords": "kw"},
            },
        }

        response = client.post("/generate", data={
            "input_type": "image",
            "text": "",
            "url": "",
        }, files={"image": ("test.jpg", b"fake-image-data", "image/jpeg")})

        assert response.status_code == 200
        assert "Indo Title" in response.text
        mock_process.assert_called_once_with(b"fake-image-data")


class TestExportCsv:
    @patch("main.process_text_input")
    def test_export_csv(self, mock_process):
        mock_process.return_value = {
            "product_info": {"name": "Test"},
            "localizations": {
                "indonesia": {"title": "Indo Title", "description": "Indo desc", "keywords": "kw"},
                "thailand": {"title": "Thai Title", "description": "Thai desc", "keywords": "kw"},
                "vietnam": {"title": "Viet Title", "description": "Viet desc", "keywords": "kw"},
                "malaysia": {"title": "MY Title", "description": "MY desc", "keywords": "kw"},
                "philippines": {"title": "PH Title", "description": "PH desc", "keywords": "kw"},
            },
        }

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
        })
        assert response.status_code == 200

        csv_response = client.get("/export-csv")
        assert csv_response.status_code == 200
        assert "text/csv" in csv_response.headers.get("content-type", "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -v`
Expected: All tests FAIL (no module named 'main')

- [ ] **Step 3: Write templates/base.html**

Create `templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Listing Localizer — Multilingual Listings for Shopee &amp; Lazada</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        {% block content %}{% endblock %}
    </div>
    <footer class="text-center py-6 text-gray-400 text-sm">
        Listing Localizer — Built for Southeast Asian sellers
    </footer>
</body>
</html>
```

- [ ] **Step 4: Write templates/index.html**

Create `templates/index.html`:

```html
{% extends "base.html" %}
{% block content %}

<div class="text-center mb-8">
    <h1 class="text-3xl font-bold text-gray-900 mb-2">Listing Localizer</h1>
    <p class="text-gray-600">One product. Five markets. Localized listings in seconds.</p>
</div>

<div class="flex gap-0 mb-0" role="tablist">
    <button class="tab-btn px-4 py-2 rounded-t-lg bg-white border border-b-0 font-medium text-gray-900"
            onclick="switchTab('text')" id="tab-text" type="button">Paste Text</button>
    <button class="tab-btn px-4 py-2 rounded-t-lg border border-b-0 text-gray-500"
            onclick="switchTab('url')" id="tab-url" type="button">Product URL</button>
    <button class="tab-btn px-4 py-2 rounded-t-lg border border-b-0 text-gray-500"
            onclick="switchTab('image')" id="tab-image" type="button">Screenshot</button>
</div>

<form hx-post="/generate" hx-target="#result" hx-indicator="#spinner"
      hx-encoding="multipart/form-data"
      class="bg-white rounded-lg shadow-sm p-6 mb-6 border border-gray-200">

    <div id="input-text" class="input-panel">
        <label class="block text-sm font-medium text-gray-700 mb-1">Product Information</label>
        <textarea name="text" rows="6" class="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Paste your product info here...&#10;&#10;Example:&#10;Wireless Bluetooth Earbuds&#10;Noise cancelling, 30hr battery life, IPX5 waterproof&#10;Comes with charging case and 3 sizes of ear tips&#10;Price: $25"></textarea>
    </div>

    <div id="input-url" class="input-panel hidden">
        <label class="block text-sm font-medium text-gray-700 mb-1">Shopee / Lazada Product URL</label>
        <input name="url" type="url" class="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
               placeholder="https://shopee.co.id/product/123456/..."
               value="{{ url or '' }}">
    </div>

    <div id="input-image" class="input-panel hidden">
        <label class="block text-sm font-medium text-gray-700 mb-1">Product Screenshot</label>
        <input name="image" type="file" accept="image/*" class="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
    </div>

    <input type="hidden" name="input_type" id="input-type" value="text">

    <button type="submit"
            class="mt-4 w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50"
            id="submit-btn">
        Generate Localized Listings
    </button>
</form>

<div id="spinner" class="htmx-indicator text-center py-8" style="display:none;">
    <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-t-transparent"></div>
    <p class="text-gray-500 mt-2">Generating your localized listings...</p>
</div>

<div id="result" class="mt-6"></div>

<script>
function switchTab(type) {
    document.querySelectorAll('.input-panel').forEach(function(el) { el.classList.add('hidden'); });
    document.getElementById('input-' + type).classList.remove('hidden');
    document.getElementById('input-type').value = type;
    document.querySelectorAll('.tab-btn').forEach(function(el) {
        el.classList.remove('bg-white', 'font-medium', 'text-gray-900');
        el.classList.add('text-gray-500');
    });
    var btn = document.getElementById('tab-' + type);
    btn.classList.add('bg-white', 'font-medium', 'text-gray-900');
    btn.classList.remove('text-gray-500');
}
</script>

{% endblock %}
```

- [ ] **Step 5: Write templates/result.html**

Create `templates/result.html`:

```html
{% if error %}
<div class="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
    <p class="font-medium">Error</p>
    <p>{{ error }}</p>
</div>
{% else %}
<div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
    <div class="flex justify-between items-center mb-6">
        <h2 class="text-xl font-bold text-gray-900">Localized Listings</h2>
        <a href="/export-csv" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium">
            Export CSV
        </a>
    </div>

    {% for market_key in ['indonesia', 'thailand', 'vietnam', 'malaysia', 'philippines'] %}
    <div class="mb-6 p-4 border border-gray-200 rounded-lg last:mb-0">
        <div class="flex justify-between items-center mb-3">
            <h3 class="font-bold text-lg text-gray-900">{{ market_names[market_key] }}</h3>
            <button onclick="copyMarket('{{ market_key }}')"
                    class="text-sm text-blue-600 hover:underline font-medium" type="button">Copy</button>
        </div>

        {% set data = localizations[market_key] %}
        {% if data.error %}
        <p class="text-red-600 text-sm">{{ data.error }}</p>
        {% else %}
        <div class="space-y-3">
            <div>
                <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Title</span>
                <p class="text-gray-900 font-medium" id="{{ market_key }}-title">{{ data.title }}</p>
            </div>
            <div>
                <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Description</span>
                <p class="text-gray-700 whitespace-pre-wrap" id="{{ market_key }}-description">{{ data.description }}</p>
            </div>
            <div>
                <span class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Keywords</span>
                <p class="text-gray-600 text-sm" id="{{ market_key }}-keywords">{{ data.keywords }}</p>
            </div>
        </div>
        {% endif %}
    </div>
    {% endfor %}
</div>

<textarea id="copy-helper" class="hidden" aria-hidden="true"></textarea>

<script>
function copyMarket(marketKey) {
    var title = document.getElementById(marketKey + '-title').textContent;
    var desc = document.getElementById(marketKey + '-description').textContent;
    var kw = document.getElementById(marketKey + '-keywords').textContent;
    var text = 'Title: ' + title + '\n\nDescription: ' + desc + '\n\nKeywords: ' + kw;
    var helper = document.getElementById('copy-helper');
    helper.classList.remove('hidden');
    helper.value = text;
    helper.select();
    document.execCommand('copy');
    helper.classList.add('hidden');

    var btn = event.target;
    var originalText = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(function() { btn.textContent = originalText; }, 1500);
}
</script>
{% endif %}
```

- [ ] **Step 6: Write main.py**

Create `main.py`:

```python
import io
import csv
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from services.llm import process_text_input, process_url_input, process_image_input
from services.scraper import scrape_product_page, is_valid_url
from prompts.localization import MARKET_NAMES

app = FastAPI(title="Listing Localizer")
app.add_middleware(SessionMiddleware, secret_key="localizer-secret-change-in-production")

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    input_type: str = Form(...),
    text: str = Form(default=""),
    url: str = Form(default=""),
    image: UploadFile | None = File(default=None),
):
    if input_type == "text":
        if not text.strip():
            return templates.TemplateResponse(
                "result.html", {"request": request, "error": "Please enter product information."}
            )
        result = process_text_input(text.strip())

    elif input_type == "url":
        if not url.strip():
            return templates.TemplateResponse(
                "result.html", {"request": request, "error": "Please enter a product URL."}
            )
        if not is_valid_url(url.strip()):
            return templates.TemplateResponse(
                "result.html", {"request": request, "error": "Invalid URL. Please use a Shopee or Lazada product page URL."}
            )
        try:
            scraped_text = scrape_product_page(url.strip())
        except Exception as e:
            return templates.TemplateResponse(
                "result.html", {"request": request, "error": f"Failed to fetch product page: {str(e)}"}
            )
        result = process_url_input(scraped_text)

    elif input_type == "image":
        if not image or not image.filename:
            return templates.TemplateResponse(
                "result.html", {"request": request, "error": "Please upload a screenshot."}
            )
        image_data = await image.read()
        if len(image_data) > 5 * 1024 * 1024:
            return templates.TemplateResponse(
                "result.html", {"request": request, "error": "Image too large. Maximum size is 5MB."}
            )
        result = process_image_input(image_data)

    else:
        return templates.TemplateResponse(
            "result.html", {"request": request, "error": f"Unknown input type: {input_type}"}
        )

    if "error" in result:
        return templates.TemplateResponse(
            "result.html", {"request": request, "error": result["error"]}
        )

    request.session["last_result"] = result

    return templates.TemplateResponse("result.html", {
        "request": request,
        "localizations": result.get("localizations", {}),
        "market_names": MARKET_NAMES,
        "error": None,
    })


@app.get("/export-csv")
def export_csv(request: Request):
    result = request.session.get("last_result")
    if not result:
        return HTMLResponse("<p class='text-red-600'>No data to export. Generate a listing first.</p>")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Market", "Language", "Title", "Description", "Keywords"])

    market_names = MARKET_NAMES
    for market_key in ["indonesia", "thailand", "vietnam", "malaysia", "philippines"]:
        data = result["localizations"].get(market_key, {})
        if "error" not in data:
            writer.writerow([
                market_key.title(),
                market_names[market_key],
                data.get("title", ""),
                data.get("description", ""),
                data.get("keywords", ""),
            ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=localized-listings.csv"},
    )
```

- [ ] **Step 7: Run route tests to verify they pass**

Run: `pytest tests/test_routes.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add main.py templates/base.html templates/index.html templates/result.html tests/test_routes.py
git commit -m "feat: add FastAPI app with HTMX frontend and 3 input modes"
```

---

### Task 6: Run and Verify

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Start the dev server**

Run: `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
Expected: Server starts on http://localhost:8000

- [ ] **Step 3: Verify text input flow**

Run: `curl -s http://localhost:8000/ | head -5`
Expected: Returns HTML with "Listing Localizer"

- [ ] **Step 4: Manual smoke test**

Open http://localhost:8000 in browser:
1. Paste "Wireless Bluetooth Earbuds, noise cancelling, 30hr battery, $25"
2. Click Generate
3. Verify 5 market cards appear with localized content

- [ ] **Step 5: Commit final changes**

```bash
git add .
git commit -m "chore: finalize MVP with passing test suite"
```

---

## Post-MVP Roadmap (Not in this plan)

1. Add user registration and login (email/password)
2. Usage tracking with free tier (3/month) and Pro ($5-10/month)
3. Chrome extension that works directly on Shopee/Lazada seller center
4. Better scraping with stealth Playwright config
5. Prompt tuning based on real user feedback from each market
