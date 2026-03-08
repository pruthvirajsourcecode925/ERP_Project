from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    clean = value.strip()
    return clean or default


def _address_lines() -> list[str]:
    raw = os.getenv("COMPANY_ADDRESS_LINES", "")
    if not raw.strip():
        return [
            "Plot no. H3/1",
            "NEARS AIMA OFFICE",
            "MIDC Ambad",
            "Nashik-422009",
        ]
    return [part.strip() for part in raw.split("|") if part.strip()]


_COMPANY_NAME = _env("COMPANY_NAME", "MAULI INDUSTRIES")
_ADDRESS_LINES = _address_lines()
_COMPANY_ADDRESS = _env("COMPANY_ADDRESS", ", ".join(_ADDRESS_LINES))
_COMPANY_EMAIL = _env("COMPANY_EMAIL", "mauliind.mfg@gmail.com")
_COMPANY_PHONE = _env("COMPANY_PHONE", "+91-9604091397")
_COMPANY_WEBSITE = _env("COMPANY_WEBSITE", "www.mauliind.mfg@gmail.com")

COMPANY_INFO = {
    "company_name": _COMPANY_NAME,
    "company_address": _COMPANY_ADDRESS,
    "company_email": _COMPANY_EMAIL,
    "company_phone": _COMPANY_PHONE,
    # Legacy keys kept for compatibility with existing generators.
    "name": _COMPANY_NAME,
    "website": _COMPANY_WEBSITE,
    "address_lines": _ADDRESS_LINES,
    "email": _COMPANY_EMAIL,
    "phone": _COMPANY_PHONE,
}

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LOGO_PATH = _PROJECT_ROOT / "assets" / "logo.png"
_LOGO_OVERRIDE = os.getenv("COMPANY_LOGO_PATH", "").strip()

if _LOGO_OVERRIDE:
    _LOGO_CANDIDATE = Path(_LOGO_OVERRIDE)
    LOGO_PATH = _LOGO_CANDIDATE if _LOGO_CANDIDATE.is_absolute() else (_PROJECT_ROOT / _LOGO_CANDIDATE)
else:
    LOGO_PATH = _DEFAULT_LOGO_PATH
