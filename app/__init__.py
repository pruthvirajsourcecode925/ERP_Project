from pathlib import Path

_backend_app_dir = Path(__file__).resolve().parent.parent / "as9100d-erp-backend" / "app"
__path__.append(str(_backend_app_dir))
