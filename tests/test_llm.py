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
