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

    def load_csv(self, csv_url: str) -> None:
        import csv as _csv
        import io as _io

        self.banks.clear()
        self.country_names.clear()
        for r in _csv.DictReader(_io.StringIO(self.fetch(csv_url))):
            cc = r["country_code"].strip().upper()
            code = r["bank_code"].strip()
            if not code:
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

    @staticmethod
    def iso7064_national(digits: str) -> str:
        """ISO 7064 MOD 97-10 national check digits (BA, ME, RS, SI)."""
        return f"{98 - (int(digits) * 100) % 97:02d}"

    @staticmethod
    def ee_check(body: str) -> str:
        """Estonian account check digit: weighted (7,3,1) mod 10 over reversed body."""
        weights = (7, 3, 1)
        r = sum(weights[i % 3] * int(c) for i, c in enumerate(reversed(body))) % 10
        return "0" if r == 0 else str(10 - r)

    @staticmethod
    def hu_check(digits: str) -> str:
        """Hungarian check digit: weights 9,7,3,1 (repeating) mod 10.

        Applied twice per BBAN — once over bank+branch, once over the account.
        Always yields a single digit, so generation is deterministically valid.
        """
        weights = (9, 7, 3, 1)
        s = sum(int(c) * weights[i % 4] for i, c in enumerate(digits))
        return str((10 - s % 10) % 10)

    @staticmethod
    def hr_check(body: str) -> str:
        """Croatian account check digit: ISO 7064 MOD 11,10 over the account body.

        Always yields a single digit (0-9), so no retry is needed.
        """
        r = 10
        for c in body:
            r = (r + int(c)) % 10
            if r == 0:
                r = 10
            r = (r * 2) % 11
        return str((11 - r) % 10)

    def wmod11_fill(self, weights: list[int]) -> str:
        """Random digit string of len(weights) whose weighted sum is 0 mod 11.

        Used for Czech/Slovak prefix and account numbers (last weight must be 1).
        """
        while True:
            head = [random.randint(0, 9) for _ in range(len(weights) - 1)]
            partial = sum(w * d for w, d in zip(weights, head))
            last = (-partial) % 11
            if last != 10:
                return "".join(map(str, head)) + str(last)

    def is_kennitala(self) -> str:
        """Icelandic 10-digit kennitala with a valid mod-11 check digit at index 8."""
        weights = (3, 2, 7, 6, 5, 4, 3, 2)
        while True:
            head = self.rand_digits(8)
            rem = sum(w * int(c) for w, c in zip(weights, head)) % 11
            chk = 0 if rem == 0 else 11 - rem
            if chk != 10:
                return head + str(chk) + self.rand_digits(1)


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

    def bban_ba(self, bank_code: str) -> tuple[str, str]:
        # BA: 3!n bank 3!n branch 8!n account 2!n ISO7064 check
        bank = bank_code.rjust(3, "0")[-3:]
        body = bank + self.rand_digits(3) + self.rand_digits(8)
        return body + self.iso7064_national(body), bank

    def bban_me_rs(self, bank_code: str) -> tuple[str, str]:
        # ME / RS: 3!n bank 13!n account 2!n ISO7064 check
        bank = bank_code.rjust(3, "0")[-3:]
        body = bank + self.rand_digits(13)
        return body + self.iso7064_national(body), bank

    def bban_si(self, bank_code: str) -> tuple[str, str]:
        # SI: 5!n bank/branch 8!n account 2!n ISO7064 check
        five = bank_code.rjust(5, "0")[-5:]
        body = five + self.rand_digits(8)
        return body + self.iso7064_national(body), five

    def bban_ee(self, bank_code: str) -> tuple[str, str]:
        # EE: 2!n bank 2!n branch 11!n account 1!n check
        bank = bank_code.rjust(2, "0")[-2:]
        branch = self.rand_digits(2)
        account = self.rand_digits(11)
        return bank + branch + account + self.ee_check(branch + account), bank

    def bban_cz_sk(self, bank_code: str) -> tuple[str, str]:
        # CZ / SK: 4!n bank 6!n prefix 10!n account (both mod-11 checked)
        bank = bank_code.rjust(4, "0")[-4:]
        prefix = self.wmod11_fill([10, 5, 8, 4, 2, 1])
        account = self.wmod11_fill([6, 3, 7, 9, 10, 5, 8, 4, 2, 1])
        return bank + prefix + account, bank

    def bban_hu(self, bank_code: str) -> tuple[str, str]:
        # HU: 3!n bank 4!n branch 1!n check(bank+branch) 15!n account 1!n check(account)
        bank = bank_code.rjust(3, "0")[-3:]
        branch = self.rand_digits(4)
        cd1 = self.hu_check(bank + branch)
        account = self.rand_digits(15)
        cd2 = self.hu_check(account)
        return bank + branch + cd1 + account + cd2, bank

    def bban_hr(self, bank_code: str) -> tuple[str, str]:
        # HR: 7!n bank (from directory, already check-valid) 9!n account 1!n check
        bank = bank_code.rjust(7, "0")[-7:]
        body = self.rand_digits(9)
        return bank + body + self.hr_check(body), bank

    def bban_is(self, bank_code: str) -> tuple[str, str]:
        # IS: 2!n bank 2!n branch 2!n type 6!n account 10!n kennitala (mod-11 checked)
        bank = bank_code.rjust(2, "0")[-2:]
        return (bank + self.rand_digits(2) + self.rand_digits(2)
                + self.rand_digits(6) + self.is_kennitala()), bank

    BBAN_BUILDERS = {
        "IT": bban_it_sm, "SM": bban_it_sm,
        "MU": bban_mu, "SC": bban_sc,
        "BE": bban_be, "ES": bban_es, "FR": bban_fr, "MC": bban_fr,
        "NO": bban_no, "FI": bban_fi, "PT": bban_pt,
        "BR": bban_br,
        "BA": bban_ba, "ME": bban_me_rs, "RS": bban_me_rs, "SI": bban_si,
        "EE": bban_ee, "CZ": bban_cz_sk, "SK": bban_cz_sk, "IS": bban_is,
        "HU": bban_hu, "HR": bban_hr,
    }
