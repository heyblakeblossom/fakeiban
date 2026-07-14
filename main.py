"""
FAKEIBAN API — generates a valid IBAN for a country. Generation logic lives in
iban.py.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import html
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from iban import IBANGenerator, UnknownCountryError

CDN = "https://cdn.jsdelivr.net/gh/heyblakee/fakeiban@main"
BANK_CSV_URL = f"{CDN}/bank_data_valid.csv"

iban_generator = IBANGenerator(BANK_CSV_URL, fetch_timeout=30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    for _ in range(3):
        try:
            iban_generator.load_csv(BANK_CSV_URL)
            break
        except Exception:
            pass
    yield


app = FastAPI(title="FAKEIBAN API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def error_response(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    err = exc.errors()[0]
    field = str(err["loc"][-1]) if err.get("loc") else "request"
    if err.get("type") == "missing":
        message = f"Field '{field}' is required."
    else:
        message = f"Field '{field}' is invalid: {err.get('msg', 'invalid value')}."
    return error_response(422, message)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return error_response(exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    return error_response(500, "An unexpected error occurred. Please try again later.")


def require_data() -> None:
    if not iban_generator.loaded:
        raise HTTPException(503, "Bank data is not loaded yet. Please try again shortly.")


@app.get("/")
def home():
    return {
        "name": "FAKEIBAN API",
        "version": "2.0.0",
        "endpoints": {
            "page": "GET /de  (country code as the path)",
            "iban": "GET /iban?country=DE",
            "countries": "GET /countries",
        },
        "supported_countries": len(iban_generator.banks),
    }


@app.get("/countries", dependencies=[Depends(require_data)])
def countries():
    out = iban_generator.countries
    return {"total": len(out), "countries": out}


@app.get("/iban", dependencies=[Depends(require_data)])
def iban(country: str = Query(..., description="ISO country code, e.g. DE")):
    try:
        result = iban_generator.generate(country).to_dict()
    except UnknownCountryError as e:
        raise HTTPException(400, str(e))
    return result


@app.get("/{country}", response_class=HTMLResponse, dependencies=[Depends(require_data)])
def country_page(country: str):
    cc = country.strip().upper()
    try:
        d = iban_generator.generate(cc).to_dict()
        body = (
            f'<div class="row"><div class="label">IBAN</div>'
            f'<div class="value">{html.escape(str(d["iban"]))}</div></div>'
            f'<div class="row"><div class="label">BIC</div>'
            f'<div class="value">{html.escape(str(d["swift_bic"]))}</div></div>'
        )
        status = 200
    except UnknownCountryError as e:
        body = (
            '<div class="err">'
            '<div class="err-title">Not found</div>'
            f'<div class="err-msg">{html.escape(str(e))}</div>'
            '<div class="err-hint">Try a country code like /de, /nl, or /gb.</div>'
            '</div>'
        )
        status = 404

    page = (
        '<!doctype html><html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'minimum-scale=1, maximum-scale=1, user-scalable=no">'
        f'<title>FAKEIBAN - {html.escape(cc)}</title>'
        '<style>'
        'body{margin:0;box-sizing:border-box;min-height:100vh;display:flex;'
        'align-items:flex-start;justify-content:center;padding:64px 16px 0;'
        'background:#f4f5f7;color:#1f2937;'
        'font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}'
        '.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;'
        'padding:26px 30px;box-shadow:0 6px 24px rgba(0,0,0,.06);max-width:90vw;}'
        '.row+.row{margin-top:16px;}'
        '.label{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;'
        'color:#6b7280;margin-bottom:4px;}'
        '.value{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        'font-size:1.15rem;font-weight:600;color:#111827;word-break:break-all;}'
        '.err{text-align:center;}'
        '.err-title{font-size:1.05rem;font-weight:700;color:#b91c1c;margin-bottom:8px;}'
        '.err-msg{color:#6b7280;font-size:.9rem;line-height:1.45;margin-bottom:10px;}'
        '.err-hint{font-size:.8rem;color:#9ca3af;}'
        '@media(prefers-color-scheme:dark){'
        'body{background:#0f172a;color:#e2e8f0;}'
        '.card{background:#1e293b;border-color:#334155;box-shadow:none;}'
        '.label{color:#94a3b8;}.value{color:#fff;}'
        '.err-title{color:#f87171;}.err-msg{color:#94a3b8;}.err-hint{color:#64748b;}}'
        '</style></head><body>'
        f'<div class="card">{body}</div>'
        '</body></html>'
    )
    return HTMLResponse(page, status_code=status)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
