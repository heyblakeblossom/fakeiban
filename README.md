# fakeiban

A public IBAN bank-code dataset and a tiny FastAPI service that generates mod-97-valid test IBANs from it.

## What it is

- **Dataset** — [`bank_data.csv`](./bank_data.csv) — real bank records across 63 countries, grouped by country.
- **API** — [`main.py`](./main.py) (endpoints) + [`iban.py`](./iban.py) (`IBANGenerator`). FastAPI returns a freshly-generated IBAN for any supported country.

## Quickstart

### Fetch the dataset (Python)

```python
import json, urllib.request

URL = "https://cdn.jsdelivr.net/gh/blkblssm/fakeiban@main/bank_data.json"
data = json.load(urllib.request.urlopen(URL))
print(data["DE"]["country_name"], data["DE"]["iban_length"])
print(data["DE"]["banks"][:3])
```

### Call the hosted API (curl)

```bash
curl "https://fakeiban.vercel.app/iban?country=DE"
```

Example response (illustrative — the API generates a new IBAN each call):

```json
{
  "country_code": "DE",
  "country_name": "Germany",
  "iban":         "DE89370400440532013000",
  "bank_code":    "37040044",
  "bank_name":    "Commerzbank",
  "swift_bic":    "COBADEFFXXX"
}
```

## Dataset schema (`bank_data.json`)

One object per country:

```json
"DE": {
  "country_name": "Germany",
  "iban_length": 22,
  "banks": [
    {"bank_code": "10000000", "swift_bic": "MARKDEF1100", "bank_name": "Bundesbank"}
  ]
}
```

| Field          | Type   | Notes                                                                     |
| -------------- | ------ | ------------------------------------------------------------------------- |
| `country_name` | string | English country name                                                      |
| `iban_length`  | int    | Official ISO 13616 length for the country (constant per country)          |
| `bank_code`    | string | National IBAN bank identifier — **string** (leading zeros matter)         |
| `swift_bic`    | string | SWIFT/BIC, 8 or 11 chars; may be empty                                    |
| `bank_name`    | string | Human-readable bank name                                                  |

## Country coverage

**61 countries, 29,329 banks.** Top 10 by bank count:

| Rank | Country | Banks | | Rank | Country | Banks |
| ---: | ------- | ----: |-| ---: | ------- | ----: |
| 1 | DK | 6,947 | | 6  | CH | 1,252 |
| 2 | DE | 3,709 | | 7  | AT |   891 |
| 3 | GB | 3,627 | | 8  | SI |   829 |
| 4 | PL | 3,154 | | 9  | BE |   826 |
| 5 | NO | 2,297 | | 10 | IE |   647 |

<details>
<summary>Full list of supported country codes (61)</summary>

AD, AE, AT, AZ, BA, BE, BG, BH, CH, CR, CY, CZ, DE, DK, DO, EE, ES, FI, FR, GB, GE, GI, GR, HR, HU, IE, IL, IQ, IS, IT, JO, KW, KZ, LC, LI, LT, LU, LV, MC, MD, ME, MT, MU, NL, NO, PK, PL, PS, PT, QA, RO, RS, SA, SC, SE, SI, SK, SV, TR, UA, VG

</details>

## API endpoints

| Method | Path                   | Description                                          |
| ------ | ---------------------- | ---------------------------------------------------- |
| GET    | `/`                    | Service metadata (version, dataset stats)            |
| GET    | `/countries`           | List of 61 supported countries                       |
| GET    | `/iban?country={code}` | Generate one mod-97-valid IBAN for the country       |
| GET    | `/{code}`              | Simple HTML page showing a generated IBAN (e.g. `/de`) |

## Hosting & CDN

The data is served by jsDelivr straight from GitHub, so no auth, account, or rate limits for normal use.

```
https://cdn.jsdelivr.net/gh/blkblssm/fakeiban@main/bank_data.csv
```

The FastAPI app fetches this at cold start, so deployments need no environment variables or bundled data files.

## Hosted API

Live at **<https://fakeiban.vercel.app/>** — deployed on Vercel via `@vercel/python` (auto-detected from `main.py` and `requirements.txt`).

```bash
curl https://fakeiban.vercel.app/iban?country=DE
curl https://fakeiban.vercel.app/countries
```

## Caveats

- **Test data only** — bank codes are real, but account numbers are randomly generated.
- **Cannot send or receive real money** — IBANs validate structurally (mod-97) but are not registered to anyone.
- **Italian IBANs** include a CIN check letter; the API computes it via the official algorithm automatically.
- **Snapshot, not live** — the dataset is a point-in-time export; banks may merge, rename, or change BICs.

## License

[MIT](./LICENSE) — Copyright (c) 2026 blkblssm.
