from unittest.mock import patch
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
