"""FIFA 3-letter country code ↔ DB team name mapping.

Single source of truth for the backend. Mirrors the frontend's
``teamCodes.ts`` TEAM_CODES dict.  Only teams that appear in our
fixtures DB need an entry — the scraper ignores FIFA-ranked teams
whose code isn't listed here.
"""

TEAM_NAME_TO_FIFA_CODE: dict[str, str] = {
    "Algeria": "ALG",
    "Argentina": "ARG",
    "Australia": "AUS",
    "Austria": "AUT",
    "Belgium": "BEL",
    "Bosnia-Herzegovina": "BIH",
    "Brazil": "BRA",
    "Canada": "CAN",
    "Cape Verde Islands": "CPV",
    "Colombia": "COL",
    "Congo DR": "COD",
    "Croatia": "CRO",
    "Curaçao": "CUW",
    "Czechia": "CZE",
    "Denmark": "DEN",
    "Ecuador": "ECU",
    "Egypt": "EGY",
    "England": "ENG",
    "France": "FRA",
    "Germany": "GER",
    "Ghana": "GHA",
    "Haiti": "HAI",
    "Iran": "IRN",
    "Iraq": "IRQ",
    "Italy": "ITA",
    "Ivory Coast": "CIV",
    "Japan": "JPN",
    "Jordan": "JOR",
    "Mexico": "MEX",
    "Morocco": "MAR",
    "Netherlands": "NED",
    "New Zealand": "NZL",
    "Norway": "NOR",
    "Panama": "PAN",
    "Paraguay": "PAR",
    "Portugal": "POR",
    "Qatar": "QAT",
    "Saudi Arabia": "KSA",
    "Scotland": "SCO",
    "Senegal": "SEN",
    "South Africa": "RSA",
    "South Korea": "KOR",
    "Spain": "ESP",
    "Sweden": "SWE",
    "Switzerland": "SUI",
    "Tunisia": "TUN",
    "Turkey": "TUR",
    "United States": "USA",
    "Uruguay": "URU",
    "Uzbekistan": "UZB",
}

FIFA_CODE_TO_TEAM_NAME: dict[str, str] = {v: k for k, v in TEAM_NAME_TO_FIFA_CODE.items()}
