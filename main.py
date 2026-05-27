import asyncio
import csv
import io
import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import (
    DAILY_FREE_LIMIT,
    SESSION_SECRET,
    STRIPE_SECRET_KEY,
    STRIPE_PRICE_ID,
    STRIPE_WEBHOOK_SECRET,
)
from services.llm import (
    process_image_input,
    process_text_input,
    process_url_input,
    regenerate_localizations,
)
from services.scraper import is_valid_url, scrape_product_page
from prompts.localization import MARKET_NAMES
from translations import LANGUAGES, t as translate
import auth
import db

MARKET_KEYS = ["indonesia", "thailand", "vietnam", "malaysia", "philippines"]

_results: dict[str, tuple[dict, float]] = {}

def _stash_result(key: str, result: dict):
    _results[key] = (result, time.time())
    cutoff = time.time() - 3600
    stale = [k for k, v in _results.items() if v[1] < cutoff]
    for k in stale:
        del _results[k]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import sys
    print(f"Starting Listing Localizer (Python {sys.version})", flush=True)
    if SESSION_SECRET == "dev-secret-change-in-production":
        print("WARNING: SESSION_SECRET is using the default value. Set it in your .env for production.", flush=True)
    try:
        db.init_db()
        print("Database initialized successfully.", flush=True)
    except Exception as e:
        print(f"ERROR initializing database: {e}", flush=True)
        raise
    yield


app = FastAPI(title="Listing Localizer", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=30 * 24 * 60 * 60, https_only=True)

templates = Jinja2Templates(directory="templates")
templates.env.globals["t"] = translate
templates.env.globals["LANGUAGES"] = LANGUAGES

_original_template_response = templates.TemplateResponse

def _template_response(request, name, context=None, **kwargs):
    if context is None:
        context = {}
    context.setdefault("lang", request.session.get("lang", "en"))
    return _original_template_response(request, name, context, **kwargs)

templates.TemplateResponse = _template_response

app.mount("/static", StaticFiles(directory="static"), name="static")


async def _ctx(request: Request) -> dict:
    user = await auth.get_current_user(request)
    return {"user": user}


# ---------- Auth routes ----------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    ctx = await _ctx(request)
    user = ctx["user"]
    if user:
        used, limit = await asyncio.to_thread(db.get_todays_usage, user["id"], bool(user["is_pro"]))
        ctx["used"] = used
        ctx["limit"] = limit
        ctx["display_limit"] = "∞" if user["is_pro"] else str(limit)
    else:
        ctx["display_limit"] = str(DAILY_FREE_LIMIT)
    return templates.TemplateResponse(request, "index.html", ctx)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", await _ctx(request))


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    lang = request.session.get("lang", "en")
    ip = request.client.host if request.client else "unknown"
    if not auth.check_login_rate_limit(ip):
        return templates.TemplateResponse(request, "login.html", {
            "error": translate("err_rate_limit", lang),
            "user": None,
        })
    user = await asyncio.to_thread(db.db_get_user_by_email, email)
    if not user or not auth.verify_password(password, user["password_hash"]):
        auth.record_login_failure(ip)
        return templates.TemplateResponse(request, "login.html", {
            "error": translate("err_invalid_login", lang),
            "user": None,
        })
    auth.record_login_success(ip)
    request.session["user_id"] = user["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html", await _ctx(request))


@app.post("/signup", response_class=HTMLResponse)
async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    lang = request.session.get("lang", "en")
    ip = request.client.host if request.client else "unknown"
    if not auth.check_signup_rate_limit(ip):
        return templates.TemplateResponse(request, "signup.html", {
            "error": translate("err_signup_limit", lang),
            "user": None,
        })
    if len(password) < 8:
        return templates.TemplateResponse(request, "signup.html", {
            "error": translate("err_short_password", lang),
            "user": None,
        })
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        return templates.TemplateResponse(request, "signup.html", {
            "error": translate("err_letters_only", lang),
            "user": None,
        })
    if not all(c.isascii() for c in password):
        return templates.TemplateResponse(request, "signup.html", {
            "error": translate("err_non_ascii", lang),
            "user": None,
        })
    try:
        user = auth.create_user(email, password)
    except ValueError:
        return templates.TemplateResponse(request, "signup.html", {
            "error": translate("err_email_registered", lang),
            "user": None,
        })
    auth.record_signup(ip)
    request.session["user_id"] = user["id"]
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.post("/set-lang")
async def set_lang(request: Request):
    data = await request.form()
    lang = data.get("lang", "en")
    if lang in LANGUAGES:
        request.session["lang"] = lang
    referer = request.headers.get("referer", "/")
    return RedirectResponse(referer, status_code=303)


# ---------- Generation routes ----------


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    input_type: str = Form(...),
    text: str = Form(default=""),
    url: str = Form(default=""),
    image: UploadFile | None = File(default=None),
    style: str = Form(default="balanced"),
    discount: int = Form(default=0),
    markets: list[str] = Form(default=[]),
):
    lang = request.session.get("lang", "en")
    user = await auth.get_current_user(request)
    if not user:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_login_required", lang),
            "user": None,
        })

    # Validate inputs before consuming daily quota
    if len(markets) < 1:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_no_markets", lang),
            "user": user,
        })

    discount_val = discount if discount > 0 else None

    if input_type == "text":
        if not text.strip():
            return templates.TemplateResponse(request, "result.html", {
                "error": translate("err_empty_text", lang),
                "user": user,
            })
    elif input_type == "url":
        if not url.strip():
            return templates.TemplateResponse(request, "result.html", {
                "error": translate("err_empty_url", lang),
                "user": user,
            })
        if not is_valid_url(url.strip()):
            return templates.TemplateResponse(request, "result.html", {
                "error": translate("err_invalid_url", lang),
                "user": user,
            })
    elif input_type == "image":
        if not image or not image.filename:
            return templates.TemplateResponse(request, "result.html", {
                "error": translate("err_image_missing", lang),
                "user": user,
            })
        image_data = await image.read()
        if len(image_data) > 5 * 1024 * 1024:
            return templates.TemplateResponse(request, "result.html", {
                "error": translate("err_image_too_large", lang),
                "user": user,
            })
    else:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_unknown_input", lang) + f" {input_type}",
            "user": user,
        })

    # Consume daily quota after input validation passes
    allowed, used, limit = await asyncio.to_thread(
        db.check_and_increment_daily_usage, user["id"], bool(user["is_pro"])
    )
    if not allowed:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_limit_reached", lang, used=used, limit=limit),
            "user": user,
        })

    if input_type == "text":
        result = await asyncio.to_thread(process_text_input, text.strip(), style, discount_val, markets)
    elif input_type == "url":
        try:
            scraped_text = await asyncio.to_thread(scrape_product_page, url.strip())
        except Exception as e:
            return templates.TemplateResponse(request, "result.html", {
                "error": translate("err_scrape_failed", lang) + f" {str(e)}",
                "user": user,
            })
        result = await asyncio.to_thread(process_url_input, scraped_text, style, discount_val, markets)
    elif input_type == "image":
        result = await asyncio.to_thread(process_image_input, image_data, style, discount_val, markets)

    if "error" in result:
        return templates.TemplateResponse(request, "result.html", {
            "error": result["error"],
            "user": user,
        })

    key = str(uuid.uuid4())
    _stash_result(key, result)
    request.session["result_key"] = key
    request.session["last_style"] = style
    request.session["last_discount"] = discount_val
    request.session["last_markets"] = markets

    input_summary = (text.strip() or url.strip() or "Image upload")[:100]
    await asyncio.to_thread(
        db.db_save_generation,
        user["id"], input_type, input_summary, style,
        discount_val, markets, json.dumps(result),
    )

    display_limit = "∞" if user["is_pro"] else str(limit)
    return templates.TemplateResponse(request, "result.html", {
        "localizations": result.get("localizations", {}),
        "market_names": MARKET_NAMES,
        "markets": markets,
        "error": None,
        "user": user,
        "used": used,
        "display_limit": display_limit,
    })


@app.post("/regenerate-same", response_class=HTMLResponse)
async def regenerate_same(request: Request):
    lang = request.session.get("lang", "en")
    user = await auth.get_current_user(request)
    if not user:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_login_required", lang),
            "user": None,
        })

    allowed, used, limit = await asyncio.to_thread(
        db.check_and_increment_daily_usage, user["id"], bool(user["is_pro"])
    )
    if not allowed:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_limit_reached", lang, used=used, limit=limit),
            "user": user,
        })

    key = request.session.get("result_key")
    entry = _results.get(key) if key else None
    prev = entry[0] if entry else None
    if not prev:
        return templates.TemplateResponse(request, "result.html", {
            "error": translate("err_no_previous", lang),
            "user": user,
        })

    product_info = prev.get("product_info", {})
    style = request.session.get("last_style", "balanced")
    discount = request.session.get("last_discount")
    markets = request.session.get("last_markets")

    result = await asyncio.to_thread(regenerate_localizations, product_info, style, discount, markets)

    if "error" in result:
        return templates.TemplateResponse(request, "result.html", {
            "error": result["error"],
            "user": user,
        })

    key = str(uuid.uuid4())
    _stash_result(key, result)
    request.session["result_key"] = key

    input_summary = json.dumps(product_info)[:100]
    await asyncio.to_thread(
        db.db_save_generation,
        user["id"], "regenerate", input_summary, style,
        discount, markets or MARKET_KEYS, json.dumps(result),
    )

    display_limit = "∞" if user["is_pro"] else str(limit)
    return templates.TemplateResponse(request, "result.html", {
        "localizations": result.get("localizations", {}),
        "market_names": MARKET_NAMES,
        "markets": markets or MARKET_KEYS,
        "error": None,
        "user": user,
        "used": used,
        "display_limit": display_limit,
    })


# ---------- History routes ----------


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request, offset: int = 0):
    lang = request.session.get("lang", "en")
    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not user["is_pro"]:
        return templates.TemplateResponse(request, "upgrade.html", {
            "user": user,
            "has_stripe": bool(STRIPE_SECRET_KEY),
        })

    limit = 20
    generations = await asyncio.to_thread(db.db_get_generations, user["id"], limit + 1, offset)
    has_more = len(generations) > limit
    if has_more:
        generations = generations[:limit]

    return templates.TemplateResponse(request, "history.html", {
        "user": user,
        "generations": generations,
        "has_more": has_more,
        "next_offset": offset + limit,
    })


@app.get("/history/{gen_id}", response_class=HTMLResponse)
async def history_detail(request: Request, gen_id: int):
    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not user["is_pro"]:
        return templates.TemplateResponse(request, "upgrade.html", {
            "user": user,
            "has_stripe": bool(STRIPE_SECRET_KEY),
        })

    gen = await asyncio.to_thread(db.db_get_generation_by_id, gen_id, user["id"])
    if not gen:
        return templates.TemplateResponse(request, "history.html", {
            "user": user,
            "generations": [],
            "has_more": False,
            "next_offset": 0,
        })

    return templates.TemplateResponse(request, "history_detail.html", {
        "user": user,
        "gen": gen,
        "market_names": MARKET_NAMES,
    })


# ---------- Account route ----------


@app.get("/account", response_class=HTMLResponse)
async def account(request: Request):
    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    used, limit = await asyncio.to_thread(db.get_todays_usage, user["id"], bool(user["is_pro"]))
    total = await asyncio.to_thread(db.db_get_generation_count, user["id"])

    return templates.TemplateResponse(request, "account.html", {
        "user": user,
        "used": used,
        "limit": limit,
        "display_limit": "∞" if user["is_pro"] else str(limit),
        "ratio": min(used / limit, 1.0) if not user["is_pro"] and limit > 0 else 0,
        "total_generations": total,
    })


# ---------- Upgrade route ----------


@app.get("/upgrade", response_class=HTMLResponse)
async def upgrade(request: Request):
    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(request, "upgrade.html", {
        "user": user,
        "has_stripe": bool(STRIPE_SECRET_KEY),
    })


# ---------- Stripe routes ----------


@app.post("/stripe/create-checkout-session")
async def create_checkout_session(request: Request):
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return HTMLResponse("<p class='text-red-600'>Stripe is not configured.</p>")

    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        metadata={"user_id": str(user["id"])},
        success_url=f"{request.base_url}stripe/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{request.base_url}stripe/cancel",
    )
    return RedirectResponse(session.url, status_code=303)


@app.get("/stripe/success", response_class=HTMLResponse)
async def stripe_success(request: Request, session_id: str = ""):
    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if STRIPE_SECRET_KEY and session_id:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            await asyncio.to_thread(
                db.db_set_pro_status,
                user["id"], True,
                s.get("customer"),
                s.get("subscription"),
            )
            user["is_pro"] = 1
        except Exception:
            pass

    return templates.TemplateResponse(request, "stripe_success.html", {"user": user})


@app.get("/stripe/cancel", response_class=HTMLResponse)
async def stripe_cancel(request: Request):
    user = await auth.get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "stripe_cancel.html", {"user": user})


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not STRIPE_SECRET_KEY or not STRIPE_WEBHOOK_SECRET:
        return HTMLResponse("Not configured", status_code=400)

    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HTMLResponse("Invalid signature", status_code=400)

    if event.type == "checkout.session.completed":
        s = event.data.object
        uid = s.metadata.get("user_id")
        if uid:
            await asyncio.to_thread(
                db.db_set_pro_status, int(uid), True,
                s.get("customer"), s.get("subscription"),
            )
    elif event.type == "customer.subscription.deleted":
        sub = event.data.object
        await asyncio.to_thread(db.db_set_pro_status_by_subscription, sub.id, False)

    return HTMLResponse("OK")


# ---------- Export route ----------


@app.get("/export-csv")
def export_csv(request: Request):
    key = request.session.get("result_key")
    entry = _results.get(key) if key else None
    result = entry[0] if entry else None
    if not result:
        return HTMLResponse("<p class='text-red-600'>No data to export. Generate a listing first.</p>")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Market", "Language", "Title", "Description", "Keywords"])

    market_names = MARKET_NAMES
    markets = request.session.get("last_markets", MARKET_KEYS)
    for market_key in markets:
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
