import io
import csv
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import SESSION_SECRET
from services.llm import process_text_input, process_url_input, process_image_input
from services.scraper import scrape_product_page, is_valid_url
from prompts.localization import MARKET_NAMES

app = FastAPI(title="Listing Localizer")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


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
                request, "result.html", {"error": "Please enter product information."}
            )
        result = process_text_input(text.strip())

    elif input_type == "url":
        if not url.strip():
            return templates.TemplateResponse(
                request, "result.html", {"error": "Please enter a product URL."}
            )
        if not is_valid_url(url.strip()):
            return templates.TemplateResponse(
                request, "result.html", {"error": "Invalid URL. Please use a Shopee or Lazada product page URL."}
            )
        try:
            scraped_text = scrape_product_page(url.strip())
        except Exception as e:
            return templates.TemplateResponse(
                request, "result.html", {"error": f"Failed to fetch product page: {str(e)}"}
            )
        result = process_url_input(scraped_text)

    elif input_type == "image":
        if not image or not image.filename:
            return templates.TemplateResponse(
                request, "result.html", {"error": "Please upload a screenshot."}
            )
        image_data = await image.read()
        if len(image_data) > 5 * 1024 * 1024:
            return templates.TemplateResponse(
                request, "result.html", {"error": "Image too large. Maximum size is 5MB."}
            )
        result = process_image_input(image_data)

    else:
        return templates.TemplateResponse(
            request, "result.html", {"error": f"Unknown input type: {input_type}"}
        )

    if "error" in result:
        return templates.TemplateResponse(
            request, "result.html", {"error": result["error"]}
        )

    request.session["last_result"] = result

    return templates.TemplateResponse(request, "result.html", {
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
