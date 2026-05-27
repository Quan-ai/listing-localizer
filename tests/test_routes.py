import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """Fresh TestClient per test — no session cookie leakage between tests."""
    with TestClient(app) as c:
        yield c


MOCK_USER = {
    "id": 1,
    "email": "test@example.com",
    "is_pro": 0,
    "password_hash": "$2b$12$placeholder",
    "stripe_customer_id": None,
    "stripe_subscription_id": None,
    "created_at": "2025-01-01T00:00:00",
}
MOCK_USER_PRO = {**MOCK_USER, "is_pro": 1}
MOCK_USAGE_ALLOWED = (True, 1, 3)
MOCK_USAGE_DENIED = (False, 3, 3)

AUTH_PATCH = "main.auth.get_current_user"
DB_USAGE_PATCH = "main.db.check_and_increment_daily_usage"
DB_SAVE_PATCH = "main.db.db_save_generation"


def _mock_auth_and_usage(mock_save, mock_usage, mock_auth):
    mock_auth.return_value = MOCK_USER
    mock_usage.return_value = MOCK_USAGE_ALLOWED
    mock_save.return_value = 1


class TestHomePage:
    def test_get_home_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Listing Localizer" in response.text


class TestAuthFlow:
    @patch("main.db.db_get_user_by_email")
    def test_login_page_returns_200(self, _mock, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert "Email" in response.text

    @patch("main.db.db_get_user_by_email")
    def test_signup_page_returns_200(self, _mock, client):
        response = client.get("/signup")
        assert response.status_code == 200
        assert "Email" in response.text

    @patch("main.auth.create_user")
    def test_signup_redirects_on_success(self, mock_create, client):
        mock_create.return_value = MOCK_USER
        response = client.post("/signup", data={
            "email": "new@example.com",
            "password": "secret123",
        }, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    @patch("main.auth.create_user")
    def test_signup_rejects_short_password(self, _mock, client):
        response = client.post("/signup", data={
            "email": "new@example.com",
            "password": "1234567",
        })
        assert response.status_code == 200
        assert "8 characters" in response.text

    @patch("main.auth.create_user")
    def test_signup_rejects_letters_only(self, _mock, client):
        response = client.post("/signup", data={
            "email": "new@example.com",
            "password": "abcdefgh",
        })
        assert response.status_code == 200
        assert "letter" in response.text.lower()

    @patch("main.auth.create_user")
    def test_signup_rejects_numbers_only(self, _mock, client):
        response = client.post("/signup", data={
            "email": "new@example.com",
            "password": "12345678",
        })
        assert response.status_code == 200
        assert "letter" in response.text.lower()

    @patch("main.auth.create_user")
    def test_signup_rejects_non_ascii(self, _mock, client):
        response = client.post("/signup", data={
            "email": "new@example.com",
            "password": "密码1234abcd",
        })
        assert response.status_code == 200
        assert "English" in response.text

    @patch("main.db.db_get_user_by_email")
    def test_login_rejects_bad_credentials(self, mock_get, client):
        mock_get.return_value = None
        response = client.post("/login", data={
            "email": "nope@example.com",
            "password": "wrong",
        })
        assert response.status_code == 200
        assert "Invalid" in response.text

    @patch("main.db.db_get_user_by_email")
    @patch("main.auth.verify_password")
    def test_login_redirects_on_success(self, mock_verify, mock_get, client):
        mock_get.return_value = MOCK_USER
        mock_verify.return_value = True
        response = client.post("/login", data={
            "email": "test@example.com",
            "password": "correct",
        }, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_logout_redirects(self, client):
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/"


class TestAuthGate:
    def test_generate_blocked_without_auth(self, client):
        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test",
            "url": "",
            "markets": ["indonesia"],
        })
        assert response.status_code == 200
        assert "log in" in response.text.lower()

    def test_regenerate_blocked_without_auth(self, client):
        response = client.post("/regenerate-same")
        assert response.status_code == 200
        assert "log in" in response.text.lower()

    def test_history_redirects_without_auth(self, client):
        response = client.get("/history", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_account_redirects_without_auth(self, client):
        response = client.get("/account", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]

    def test_upgrade_redirects_without_auth(self, client):
        response = client.get("/upgrade", follow_redirects=False)
        assert response.status_code == 303
        assert "/login" in response.headers["location"]


class TestDailyLimit:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_blocks_when_limit_reached(self, mock_process, mock_auth, mock_usage, mock_save, client):
        mock_auth.return_value = MOCK_USER
        mock_usage.return_value = MOCK_USAGE_DENIED

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
            "markets": ["indonesia"],
        })

        assert response.status_code == 200
        assert "3/3" in response.text or "free generations" in response.text.lower()
        mock_process.assert_not_called()

    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_allows_when_under_limit(self, mock_process, mock_auth, mock_usage, mock_save, client):
        mock_process.return_value = {
            "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
            "localizations": {
                "indonesia": {"title": "Indo Title", "description": "Desc", "keywords": "kw"},
            },
        }
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
            "markets": ["indonesia"],
        })

        assert response.status_code == 200
        assert "Indo Title" in response.text
        mock_process.assert_called_once()

    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_pro_user_always_allowed(self, mock_process, mock_auth, mock_usage, mock_save, client):
        mock_auth.return_value = MOCK_USER_PRO
        mock_usage.return_value = (True, 0, 999_999)
        mock_save.return_value = 1
        mock_process.return_value = {
            "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
            "localizations": {
                "indonesia": {"title": "Pro Title", "description": "Desc", "keywords": "kw"},
            },
        }

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
            "markets": ["indonesia"],
        })

        assert response.status_code == 200
        assert "Pro Title" in response.text


class TestGenerateTextInput:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_generates_from_text(self, mock_process, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)
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
            "markets": ["indonesia", "thailand", "vietnam", "malaysia", "philippines"],
        })

        assert response.status_code == 200
        assert "Indo Title" in response.text
        assert "Thai Title" in response.text
        mock_process.assert_called_once_with("Test product", "balanced", None, ["indonesia", "thailand", "vietnam", "malaysia", "philippines"])

    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_handles_empty_text(self, mock_process, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)
        mock_process.return_value = {"error": "No content provided"}

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "",
            "url": "",
            "markets": ["indonesia"],
        })

        assert response.status_code == 200
        assert "error" in response.text.lower()


class TestGenerateUrlInput:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_url_input")
    @patch("main.scrape_product_page")
    @patch("main.is_valid_url")
    def test_generates_from_url(self, mock_valid, mock_scrape, mock_process, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)
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
            "markets": ["indonesia", "thailand"],
        })

        assert response.status_code == 200
        assert "Indo Title" in response.text

    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    def test_rejects_invalid_url(self, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)

        response = client.post("/generate", data={
            "input_type": "url",
            "text": "",
            "url": "https://example.com/product",
            "markets": ["indonesia"],
        })

        assert response.status_code == 200
        assert "Invalid" in response.text or "invalid" in response.text.lower()


class TestGenerateImageInput:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_image_input")
    def test_generates_from_image(self, mock_process, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)
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
            "markets": ["indonesia", "vietnam", "philippines"],
        }, files={"image": ("test.jpg", b"fake-image-data", "image/jpeg")})

        assert response.status_code == 200
        assert "Indo Title" in response.text
        mock_process.assert_called_once_with(b"fake-image-data", "balanced", None, ["indonesia", "vietnam", "philippines"])


class TestExportCsv:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_export_csv(self, mock_process, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)
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
            "markets": ["indonesia", "thailand", "vietnam", "malaysia", "philippines"],
        })
        assert response.status_code == 200

        csv_response = client.get("/export-csv")
        assert csv_response.status_code == 200
        assert "text/csv" in csv_response.headers.get("content-type", "")


class TestMarketValidation:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    def test_rejects_empty_markets(self, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)

        response = client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
            "markets": [],
        })

        assert response.status_code == 200
        assert "market" in response.text.lower()


class TestRegenerateSame:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    def test_regenerates_with_stored_params(self, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)

        with patch("main.process_text_input") as mock_process:
            mock_process.return_value = {
                "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
                "localizations": {
                    "indonesia": {"title": "Indo Title", "description": "Indo desc", "keywords": "kw"},
                    "thailand": {"title": "Thai Title", "description": "Thai desc", "keywords": "kw"},
                },
            }

            client.post("/generate", data={
                "input_type": "text",
                "text": "Test product",
                "url": "",
                "markets": ["indonesia", "thailand"],
                "style": "promotional",
                "discount": "30",
            })

        with patch("main.regenerate_localizations") as mock_regen:
            mock_regen.return_value = {
                "product_info": {"name": "Test"},
                "localizations": {
                    "indonesia": {"title": "New Indo Title", "description": "New desc", "keywords": "kw"},
                    "thailand": {"title": "New Thai Title", "description": "New desc", "keywords": "kw"},
                },
            }

            response = client.post("/regenerate-same")

            assert response.status_code == 200
            assert "New Indo Title" in response.text
            assert "New Thai Title" in response.text
            mock_regen.assert_called_once_with(
                {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
                "promotional", 30, ["indonesia", "thailand"]
            )

    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    def test_returns_error_without_prior_generation(self, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)

        response = client.post("/regenerate-same")
        assert response.status_code == 200
        assert "No previous result" in response.text


class TestHistoryRoutes:
    @patch(DB_SAVE_PATCH)
    @patch(DB_USAGE_PATCH)
    @patch(AUTH_PATCH)
    @patch("main.process_text_input")
    def test_history_shows_generations(self, mock_process, mock_auth, mock_usage, mock_save, client):
        _mock_auth_and_usage(mock_save, mock_usage, mock_auth)
        mock_process.return_value = {
            "product_info": {"name": "Test", "category": "Test", "key_features": [], "specs": "", "price_hint": ""},
            "localizations": {
                "indonesia": {"title": "Indo Title", "description": "Desc", "keywords": "kw"},
            },
        }

        client.post("/generate", data={
            "input_type": "text",
            "text": "Test product",
            "url": "",
            "markets": ["indonesia"],
        })

        with patch("main.db.db_get_generations") as mock_list:
            mock_list.return_value = [{
                "id": 1, "input_type": "text", "input_summary": "Test product",
                "style": "balanced", "markets": '["indonesia"]', "created_at": "2025-01-01T00:00:00",
            }]
            response = client.get("/history")
            assert response.status_code == 200


class TestAccountRoute:
    @patch("main.db.get_todays_usage")
    @patch("main.db.db_get_generation_count")
    @patch(AUTH_PATCH)
    def test_account_shows_usage(self, mock_auth, mock_count, mock_usage, client):
        mock_auth.return_value = MOCK_USER
        mock_usage.return_value = (2, 3)
        mock_count.return_value = 15

        response = client.get("/account")
        assert response.status_code == 200
        assert "2" in response.text
        assert "3" in response.text
        assert "15" in response.text


class TestUpgradeRoute:
    @patch(AUTH_PATCH)
    def test_upgrade_page_renders(self, mock_auth, client):
        mock_auth.return_value = MOCK_USER

        response = client.get("/upgrade")
        assert response.status_code == 200
        assert "Pro" in response.text
