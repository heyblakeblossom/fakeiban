"""
FAKEIBAN API — generates a structurally-valid IBAN (with a matching random
address) for a country. Generation logic lives in iban.py and address.py.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from iban import IBANGenerator, UnknownCountryError
from address import AddressGenerator

CDN = "https://cdn.jsdelivr.net/gh/blkblossom/fakeiban@main"
iban_generator = IBANGenerator(f"{CDN}/bank_data.json", fetch_timeout=30)
address_generator = AddressGenerator(f"{CDN}/address_data.json", fetch_timeout=30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Multi-MB data files load from a CDN; retry so a transient slow response
    # doesn't permanently disable a feature (e.g. silently null addresses).
    for gen in (iban_generator, address_generator):
        for _ in range(3):
            try:
                gen.load()
                break
            except Exception:
                pass
    yield


app = FastAPI(title="FAKEIBAN API", version="1.0.0", lifespan=lifespan)
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


def address_for(country: str) -> dict | None:
    if not address_generator.loaded:
        return None
    try:
        address = address_generator.generate(country).to_dict()
    except Exception:
        return None
    address.pop("country_code", None)
    address.pop("country_name", None)
    return address


@app.get("/")
def home():
    return {
        "name": "FAKEIBAN API",
        "version": "1.0.0",
        "endpoints": {"iban": "GET /iban?country=DE", "countries": "GET /countries"},
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
    result["address"] = address_for(country)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
