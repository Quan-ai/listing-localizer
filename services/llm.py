import io
import json
from openai import OpenAI
from PIL import Image
import pytesseract
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, TEXT_MODEL, LLM_TIMEOUT
from prompts.localization import EXTRACTION_PROMPT, MARKET_PROMPTS, get_style_instruction

_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if __import__("os").path.exists(_TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_PATH

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=LLM_TIMEOUT)

MARKET_ORDER = ["indonesia", "thailand", "vietnam", "malaysia", "philippines"]


def _parse_json_response(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(content)


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
    return _parse_json_response(response.choices[0].message.content)


def localize_for_market(product_info: dict, market: str, style: str = "balanced", discount: int | None = None) -> dict:
    base_prompt = MARKET_PROMPTS.get(market, MARKET_PROMPTS["indonesia"])
    style_instruction = get_style_instruction(style, discount)
    prompt = f"{base_prompt}\n\nTone style: {style_instruction}"
    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(product_info, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return _parse_json_response(response.choices[0].message.content)


def extract_from_image(image_data: bytes) -> dict:
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "Tesseract OCR is not installed. Install it from "
            "https://github.com/UB-Mannheim/tesseract/wiki "
            "or run: winget install UB-Mannheim.Tesseract"
        )

    image = Image.open(io.BytesIO(image_data))
    ocr_text = pytesseract.image_to_string(image).strip()
    if not ocr_text:
        raise RuntimeError(
            "No text could be extracted from the image. "
            "Ensure the screenshot contains readable product text, "
            "or use Text / URL input instead."
        )
    return extract_product_info(ocr_text[:4000])


def _localize_all_markets(product_info: dict, style: str = "balanced", discount: int | None = None, markets: list[str] | None = None) -> dict:
    target_markets = markets if markets else MARKET_ORDER
    results = {}
    for market in target_markets:
        try:
            results[market] = localize_for_market(product_info, market, style, discount)
        except Exception as e:
            results[market] = {"error": f"Failed for {market}: {str(e)}"}
    return results


def process_text_input(text: str, style: str = "balanced", discount: int | None = None, markets: list[str] | None = None) -> dict:
    try:
        product_info = extract_product_info(text)
    except Exception as e:
        return {"error": f"Failed to extract product info: {str(e)}"}
    return {"product_info": product_info, "localizations": _localize_all_markets(product_info, style, discount, markets)}


def process_url_input(scraped_text: str, style: str = "balanced", discount: int | None = None, markets: list[str] | None = None) -> dict:
    return process_text_input(scraped_text, style, discount, markets)


def process_image_input(image_data: bytes, style: str = "balanced", discount: int | None = None, markets: list[str] | None = None) -> dict:
    try:
        product_info = extract_from_image(image_data)
    except Exception as e:
        return {"error": f"Failed to extract product info from image: {str(e)}"}
    return {"product_info": product_info, "localizations": _localize_all_markets(product_info, style, discount, markets)}


def regenerate_localizations(product_info: dict, style: str, discount: int | None = None, markets: list[str] | None = None) -> dict:
    return {"product_info": product_info, "localizations": _localize_all_markets(product_info, style, discount, markets)}
