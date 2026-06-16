"""
Address generation utilities for the FAKEIBAN API.

Loads address_data.json — one object per country:

    "DE": {
      "country_name": "Germany",
      "phone_format": "+49-XXX-XXXXXXX",
      "streets":   ["Hauptstraße", ...],
      "locations": [{"city": "München", "region": "Bayern", "postcode": "80331"}, ...]
    }

Each location is a real (city, region, postcode) tuple sourced from GeoNames, so
the generated city/region/postcode are always a genuine, consistent combination.
The street is a real street name for that country plus a random house number.

Usage:
    gen = AddressGenerator(JSON_URL)
    gen.load()
    result = gen.generate("DE")   # AddressResult dataclass
    payload = result.to_dict()
"""
from __future__ import annotations

import json
import random
import urllib.request
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class AddressResult:
    country_code: str
    country_name: str
    street: str
    city: str
    region: str
    postcode: str
    phone: str

    def to_dict(self) -> dict:
        return asdict(self)


class UnknownAddressCountryError(ValueError):
    """Raised when generate() is called with an unsupported country code."""


class AddressGenerator:
    """Loads per-country address data (JSON) and generates real, consistent
    addresses — same load/loaded/countries/generate/to_dict shape as IBANGenerator."""

    def __init__(self, json_url: str, fetch_timeout: float = 5.0) -> None:
        self.json_url = json_url
        self.fetch_timeout = fetch_timeout
        self.data: dict[str, dict] = {}

    @property
    def loaded(self) -> bool:
        return bool(self.data)

    @property
    def countries(self) -> list[dict]:
        return sorted(
            ({"country_code": cc, "country_name": d.get("country_name", cc)}
             for cc, d in self.data.items()),
            key=lambda x: x["country_code"],
        )

    def load(self) -> None:
        self.data = json.loads(self.fetch(self.json_url))
        if not self.data:
            raise RuntimeError("Loaded address data is empty")

    def generate(self, country: str) -> AddressResult:
        cc = country.strip().upper()
        d = self.data.get(cc)
        locations = d.get("locations") if d else None
        if not locations:
            raise UnknownAddressCountryError(
                f"Unknown or unsupported country code: {country}")

        loc = random.choice(locations)           # real city + region + postcode
        streets = d.get("streets", [])
        street_name = random.choice(streets) if streets else ""
        house = random.randint(1, 9999)
        street = f"{house} {street_name}" if street_name else str(house)

        return AddressResult(
            country_code=cc,
            country_name=d.get("country_name", cc),
            street=street,
            city=loc["city"],
            region=loc["region"],
            postcode=loc["postcode"],
            phone=self.phone(d),
        )

    def fetch(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=self.fetch_timeout) as r:
            return r.read().decode("utf-8")

    @staticmethod
    def phone(d: dict) -> str:
        fmt = d.get("phone_format", "+X-XXX-XXX-XXXX")
        number = "".join(str(random.randint(0, 9)) if ch == "X" else ch for ch in fmt)
        return number.replace("-", "").replace(" ", "")
