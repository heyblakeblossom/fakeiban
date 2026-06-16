"""
IBAN generation utilities for the FAKEIBAN API.

Loads bank_data.json — one object per country:

    "DE": {
      "country_name": "Germany",
      "iban_length": 22,
      "banks": [{"bank_code": "10000000", "swift_bic": "MARKDEF1100",
                 "bank_name": "Bundesbank"}, ...]
    }

and builds structurally-valid IBANs per ISO 13616.

Usage:
    gen = IBANGenerator(JSON_URL)
    gen.load()
    result = gen.generate("DE")   # IBANResult dataclass
    payload = result.to_dict()
"""
from __future__ import annotations

import json
import random
import string
import urllib.request
from dataclasses import dataclass, asdict


ITALIAN_ODD = {
    "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
    "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21,
    "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14,
    "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23,
}


@dataclass(frozen=True)
class Bank:
    bank_code: str
    swift_bic: str
    bank_name: str
    iban_length: int


@dataclass(frozen=True)
class IBANResult:
    country_code: str
    country_name: str
    iban: str
    bank_code: str
    bank_name: str
    swift_bic: str

    def to_dict(self) -> dict:
        return asdict(self)


class UnknownCountryError(ValueError):
    """Raised when /iban is called with an unsupported country code."""


class IBANGenerator:
    """Loads per-country bank data (JSON) and generates structurally-valid IBANs."""

    def __init__(self, json_url: str, fetch_timeout: float = 5.0) -> None:
        self.json_url = json_url
        self.fetch_timeout = fetch_timeout
        self.banks: dict[str, list[Bank]] = {}
        self.country_names: dict[str, str] = {}

    @property
    def loaded(self) -> bool:
        return bool(self.banks)

    @property
    def countries(self) -> list[dict]:
        return sorted(
            ({"country_code": cc, "country_name": self.country_names[cc]}
             for cc in self.banks),
            key=lambda x: x["country_code"],
        )

    def load(self) -> None:
        data = json.loads(self.fetch(self.json_url))
        self.banks.clear()
        self.country_names.clear()
        for cc, info in data.items():
            cc = cc.strip().upper()
            length = int(info["iban_length"])
            self.country_names[cc] = info.get("country_name", cc)
            for b in info.get("banks", []):
                if not b.get("bank_code"):
                    continue
                self.banks.setdefault(cc, []).append(Bank(
                    bank_code=b["bank_code"].strip(),
                    swift_bic=(b.get("swift_bic") or "").strip(),
                    bank_name=(b.get("bank_name") or "").strip(),
                    iban_length=length,
                ))
        if not self.banks:
            raise RuntimeError("Loaded data is empty")

    def load_csv(self, csv_url: str, allowlist_url: str | None = None) -> None:
        import csv as _csv
        import io as _io

        allow: dict[str, set] = {}
        if allowlist_url:
            try:
                allow = {cc: set(v) for cc, v in json.loads(self.fetch(allowlist_url)).items()}
            except Exception:
                allow = {}

        self.banks.clear()
        self.country_names.clear()
        for r in _csv.DictReader(_io.StringIO(self.fetch(csv_url))):
            cc = r["country_code"].strip().upper()
            code = r["bank_code"].strip()
            if not code or (cc in allow and code not in allow[cc]):
                continue
            self.country_names[cc] = r["country_name"].strip()
            self.banks.setdefault(cc, []).append(Bank(
                bank_code=code,
                swift_bic=(r.get("swift_bic") or "").strip(),
                bank_name=(r.get("bank_name") or "").strip(),
                iban_length=int(r["iban_length"]),
            ))
        if not self.banks:
            raise RuntimeError("Loaded CSV data is empty")

    def generate(self, country: str) -> IBANResult:
        cc = country.strip().upper()
        if cc not in self.banks:
            raise UnknownCountryError(
                f"Unknown or unsupported country code: {country}")
        bank = random.choice(self.banks[cc])
        bban, effective = self.build_bban(cc, bank.bank_code, bank.iban_length)
        iban = cc + self.compute_check(cc, bban) + bban
        assert len(iban) == bank.iban_length and self.mod97(iban) == 1
        return IBANResult(
            country_code=cc,
            country_name=self.country_names[cc],
            iban=iban,
            bank_code=effective,
            bank_name=bank.bank_name,
            swift_bic=bank.swift_bic,
        )


    def fetch(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=self.fetch_timeout) as r:
            return r.read().decode("utf-8")


    @staticmethod
    def letters_to_numbers(s: str) -> str:
        return "".join(str(ord(c) - 55) if c.isalpha() else c for c in s.upper())

    @classmethod
    def mod97(cls, iban: str) -> int:
        return int(cls.letters_to_numbers(iban[4:] + iban[:4])) % 97

    @classmethod
    def compute_check(cls, country: str, bban: str) -> str:
        n = int(cls.letters_to_numbers(bban + country + "00")) % 97
        return f"{98 - n:02d}"

    @staticmethod
    def rand_digits(n: int) -> str:
        return "".join(random.choices(string.digits, k=n))


    @staticmethod
    def italian_cin(tail22: str) -> str:
        total = 0
        for i, c in enumerate(tail22, start=1):
            if i % 2 == 1:
                total += ITALIAN_ODD[c]
            else:
                total += int(c) if c.isdigit() else (ord(c) - ord("A"))
        return chr(ord("A") + total % 26)

    @staticmethod
    def be_check(bank3: str, acct7: str) -> str:
        n = int(bank3 + acct7) % 97
        return f"{n or 97:02d}"

    @staticmethod
    def es_control(d10: str) -> str:
        weights = [1, 2, 4, 8, 5, 10, 9, 7, 3, 6]
        total = sum(int(c) * w for c, w in zip(d10, weights))
        r = 11 - (total % 11)
        return "1" if r == 10 else "0" if r == 11 else str(r)

    @staticmethod
    def fr_rib(bank5: str, branch5: str, account11: str) -> str:
        return f"{97 - (int(bank5 + branch5 + account11) * 100) % 97:02d}"

    @staticmethod
    def no_check(d10: str) -> str | None:
        weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(c) * w for c, w in zip(d10, weights))
        r = 11 - (total % 11)
        if r == 10:
            return None
        return "0" if r == 11 else str(r)

    @staticmethod
    def fi_check(d13: str) -> str:
        total = 0
        for i, c in enumerate(reversed(d13 + "0")):
            n = int(c)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return str((10 - total % 10) % 10)

    @staticmethod
    def pt_check(d19: str) -> str:
        return f"{98 - int(d19 + '00') % 97:02d}"


    def build_bban(self, country: str, bank_code: str,
                   iban_length: int) -> tuple[str, str]:
        builder = self.BBAN_BUILDERS.get(country)
        if builder is not None:
            return builder(self, bank_code)
        fill = iban_length - 4 - len(bank_code)
        if fill < 0:
            raise ValueError(f"{country} bank_code longer than BBAN")
        return bank_code + self.rand_digits(fill), bank_code


    def bban_it_sm(self, bank_code: str) -> tuple[str, str]:
        abi = bank_code.rjust(5, "0")[-5:]
        tail = abi + self.rand_digits(5) + self.rand_digits(12)
        return self.italian_cin(tail) + tail, abi

    def bban_mu(self, bank_code: str) -> tuple[str, str]:
        bc = bank_code[:4].upper()
        return bc + self.rand_digits(19) + random.choice(["MUR", "USD", "EUR"]), bc

    def bban_sc(self, bank_code: str) -> tuple[str, str]:
        bc = bank_code[:4].upper()
        return bc + self.rand_digits(20) + random.choice(["SCR", "USD", "EUR"]), bc

    def bban_be(self, bank_code: str) -> tuple[str, str]:
        bank = bank_code.rjust(3, "0")[-3:]
        acct = self.rand_digits(7)
        return bank + acct + self.be_check(bank, acct), bank

    def bban_es(self, bank_code: str) -> tuple[str, str]:
        entity = bank_code.rjust(4, "0")[-4:]
        office = self.rand_digits(4)
        d1 = self.es_control("00" + entity + office)
        account = self.rand_digits(10)
        d2 = self.es_control(account)
        return entity + office + d1 + d2 + account, entity

    def bban_fr(self, bank_code: str) -> tuple[str, str]:
        bank = bank_code.rjust(5, "0")[-5:]
        branch = self.rand_digits(5)
        account = self.rand_digits(11)
        return bank + branch + account + self.fr_rib(bank, branch, account), bank

    def bban_no(self, bank_code: str) -> tuple[str, str]:
        bank = bank_code.rjust(4, "0")[-4:]
        tries = 0
        while tries < 50:
            acct = self.rand_digits(6)
            check = self.no_check(bank + acct)
            if check is not None:
                return bank + acct + check, bank
            tries += 1
        raise RuntimeError("NO: could not generate a mod-11 check after 50 tries")

    def bban_fi(self, bank_code: str) -> tuple[str, str]:
        bank = bank_code.rjust(6, "0")[-6:]
        acct = self.rand_digits(7)
        return bank + acct + self.fi_check(bank + acct), bank

    def bban_pt(self, bank_code: str) -> tuple[str, str]:
        bank = bank_code.rjust(4, "0")[-4:]
        branch = self.rand_digits(4)
        account = self.rand_digits(11)
        return bank + branch + account + self.pt_check(bank + branch + account), bank

    def bban_br(self, bank_code: str) -> tuple[str, str]:
        # BR2!n 8!n(bank) 5!n(branch) 10!n(account) 1!a(account type) 1!c(owner)
        bank = bank_code.rjust(8, "0")[-8:]
        branch = self.rand_digits(5)
        account = self.rand_digits(10)
        acct_type = random.choice(string.ascii_uppercase)
        owner = random.choice(string.ascii_uppercase + string.digits)
        return bank + branch + account + acct_type + owner, bank

    BBAN_BUILDERS = {
        "IT": bban_it_sm, "SM": bban_it_sm,
        "MU": bban_mu, "SC": bban_sc,
        "BE": bban_be, "ES": bban_es, "FR": bban_fr,
        "NO": bban_no, "FI": bban_fi, "PT": bban_pt,
        "BR": bban_br,
    }
