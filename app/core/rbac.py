VALID_MODULE_KEYS: tuple[str, ...] = (
    "auth",
    "users",
    "roles",
    "sales",
    "purchase",
    "engineering",
    "quality",
    "production",
    "maintenance",
    "dispatch",
)


DEFAULT_ROLE_MODULES: dict[str, list[str]] = {
    "Admin": list(VALID_MODULE_KEYS),
    "Engineering": ["engineering"],
    "Sales": ["sales"],
    "Purchase": ["purchase"],
    "Quality": ["quality"],
    "Production": ["production"],
    "Maintenance": ["maintenance"],
    "Dispatch": ["dispatch"],
    "Auditor": [],
}


def normalize_module_key(module_key: str) -> str:
    return module_key.strip().lower()
