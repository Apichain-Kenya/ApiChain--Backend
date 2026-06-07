# app/services/geocode.py
import requests

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"


def reverse_geocode(latitude: float, longitude: float) -> str | None:
    """Reverse-geocode apiary coords to a human place string for the consumer
    scan page. Fail-soft (returns None on ANY error) — never block /verify.
    Nominatim ToS requires a custom User-Agent (the project uses 'AgriScanAI-App')."""
    try:
        r = requests.get(_NOMINATIM, params={
            "lat": latitude, "lon": longitude, "format": "json", "zoom": 10,
        }, headers={"User-Agent": "AgriScanAI-App"}, timeout=8)
        if r.status_code != 200:
            return None
        addr = (r.json() or {}).get("address", {})
        parts = [addr.get("county") or addr.get("city") or addr.get("town"),
                 addr.get("state"), addr.get("country")]
        parts = [p for p in parts if p]
        return ", ".join(parts) or None
    except Exception:
        return None
