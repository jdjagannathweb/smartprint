import io
import re
import base64
import urllib.parse
import qrcode
from PIL import Image

def clean_ascii_text(text: str, fallback: str = "Smart Print") -> str:
    """Removes non-ASCII characters so UPI apps do not reject the intent."""
    if not text:
        return fallback
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", text).strip()
    return cleaned if cleaned else fallback

def generate_upi_uri(upi_id: str, merchant_name: str, amount: float, order_id: str, note: str = "Print") -> str:
    """
    Constructs a 100% NPCI compliant UPI Intent URI.
    Format: upi://pay?pa=...&pn=...&am=...&cu=INR&tn=...&mode=02
    NO non-ASCII chars in pn, NO hash (#) or special characters in tn.
    """
    clean_vpa = upi_id.strip()
    clean_pn = clean_ascii_text(merchant_name, "Smart Print")
    clean_tn = f"Order_{re.sub(r'[^a-zA-Z0-9]', '', order_id)}"

    params = [
        ("pa", clean_vpa),
        ("pn", clean_pn),
        ("am", f"{amount:.2f}"),
        ("cu", "INR"),
        ("tn", clean_tn),
        ("mode", "02")
    ]
    query_string = urllib.parse.urlencode(params)
    return f"upi://pay?{query_string}"

def generate_qr_base64(data_url: str, box_size: int = 10, border: int = 2) -> str:
    """Generates a high-contrast base64 encoded PNG image for the given URL/data."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border
    )
    qr.add_data(data_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"

def generate_counter_qr(base_url: str) -> str:
    """Generates the QR code for customers to scan at the counter."""
    return generate_qr_base64(base_url, box_size=12, border=3)
