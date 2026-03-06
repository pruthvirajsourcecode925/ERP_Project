from __future__ import annotations

from pathlib import Path

_COMPANY_NAME = "MAULI INDUSTRIES"
_ADDRESS_LINES = [
    "Plot no. H3/1",
    "NEARS AIMA OFFICE",
    "MIDC Ambad",
    "Nashik-422009",
]
_COMPANY_ADDRESS = ", ".join(_ADDRESS_LINES)
_COMPANY_EMAIL = "mauliind.mfg@gmail.com"
_COMPANY_PHONE = "+91-9604091397"

COMPANY_INFO = {
    "company_name": _COMPANY_NAME,
    "company_address": _COMPANY_ADDRESS,
    "company_email": _COMPANY_EMAIL,
    "company_phone": _COMPANY_PHONE,
    # Legacy keys kept for compatibility with existing generators.
    "name": _COMPANY_NAME,
    "website": "www.mauliind.mfg@gmail.com",
    "address_lines": _ADDRESS_LINES,
    "email": _COMPANY_EMAIL,
    "phone": _COMPANY_PHONE,
}

LOGO_PATH = Path(__file__).resolve().parents[3] / "assets" / "logo.png"
