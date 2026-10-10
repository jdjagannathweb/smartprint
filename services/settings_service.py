import json
from pathlib import Path
from services.printer_service import get_installed_printers

SETTINGS_FILE = Path(__file__).parent.parent / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "shop_name": "ସ୍ମାର୍ଟ ପ୍ରିଣ୍ଟ & ଜେରକ୍ସ ପଏଣ୍ଟ",
    "upi_id": "9937037131@ybl",
    "upi_name": "Smart Print",
    "shop_qr_image": "",
    "rate_bw": 2.0,
    "rate_color": 10.0,
    "selected_printer": "",
    "auto_print": False,
    "admin_pin": "1234",
    "currency": "₹"
}

def load_settings():
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            if not data.get("selected_printer"):
                info = get_installed_printers()
                data["selected_printer"] = info.get("default") or ""
            return data
    except Exception as e:
        print(f"Error loading settings: {e}")
        return DEFAULT_SETTINGS.copy()

def save_settings(new_settings):
    try:
        current = load_settings()
        current.update(new_settings)
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
        return {"success": True, "settings": current}
    except Exception as e:
        return {"success": False, "error": str(e)}
