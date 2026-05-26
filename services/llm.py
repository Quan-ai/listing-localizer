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
