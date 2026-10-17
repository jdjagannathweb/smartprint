import os
import subprocess
import json
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SUMATRA_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe"
if not SUMATRA_PATH.exists():
    which_sumatra = shutil.which("SumatraPDF.exe")
    if which_sumatra:
        SUMATRA_PATH = Path(which_sumatra)

def get_installed_printers():
    """Returns list of installed Windows printers and the system default printer."""
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Printer | Select-Object Name, Default, PortName, DriverName | ConvertTo-Json -Compress"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw = res.stdout.strip()
        if not raw:
            return {"printers": [], "default": None}
        
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        
        printers = []
        default_printer = None
        for p in data:
            name = p.get("Name")
            is_default = bool(p.get("Default", False))
            if name:
                printers.append({
                    "name": name,
                    "default": is_default,
                    "port": p.get("PortName", ""),
                    "driver": p.get("DriverName", "")
                })
                if is_default:
                    default_printer = name
        
        return {"printers": printers, "default": default_printer}
    except Exception as e:
        print(f"Error getting printers: {e}")
        return {"printers": [], "default": None, "error": str(e)}

def print_pdf(file_path, printer_name=None, copies=1, color_mode="bw", print_side="single"):
    """
    Silently prints a PDF file using SumatraPDF on Windows.
    color_mode: 'bw' or 'color'
    print_side: 'single' or 'double'
    """
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}
    
    sumatra = SUMATRA_PATH if SUMATRA_PATH.exists() else None
    if not sumatra:
        try:
            ps_cmd = f'Start-Process -FilePath "{file_path}" -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden'
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=True)
            return {"success": True, "method": "powershell"}
        except Exception as e:
            return {"success": False, "error": f"SumatraPDF not found and PowerShell fallback failed: {e}"}
    
    settings = []
    if copies > 1:
        settings.append(f"{copies}x")
    if color_mode == "bw":
        settings.append("monochrome")
    elif color_mode == "color":
        settings.append("color")
    
    if print_side == "double":
        settings.append("duplex")
    else:
        settings.append("simplex")
    
    cmd = [str(sumatra)]
    if printer_name and printer_name != "Default":
        cmd.extend(["-print-to", printer_name])
    else:
        cmd.append("-print-to-default")
    
    if settings:
        cmd.extend(["-print-settings", ",".join(settings)])
    
    cmd.extend(["-silent", str(file_path)])
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "success": proc.returncode == 0,
            "cmd": " ".join(cmd),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "method": "sumatra"
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Print job timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def generate_test_page_pdf(printer_name: str = "System Default", shop_name: str = "Smart Print", output_path: str = None, shop_id: str = "", connector_token: str = "", mobile: str = "") -> str:
    """Generates an A4 minimal test print PDF showing only Shop ID, Token, and credentials."""
    if output_path:
        pdf_path = Path(output_path).resolve()
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = Path(__file__).parent.parent / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = target_dir / "test_print_page.pdf"
    
    # A4 at 150 DPI = 1240 x 1754
    width, height = 1240, 1754
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Try high quality fonts, fallback gracefully
    def get_font(size, bold=False):
        font_names = ["arialbd.ttf" if bold else "arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "segoeuib.ttf" if bold else "segoeui.ttf"]
        for fn in font_names:
            try:
                return ImageFont.truetype(fn, size)
            except Exception:
                pass
        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()

    font_title = get_font(38, bold=True)
    font_label = get_font(28, bold=True)
    font_val = get_font(28, bold=False)
    font_note = get_font(22, bold=False)

    # Top border / title
    draw.text((100, 100), "SMART PRINT - TEST PAGE", fill=(0, 0, 0), font=font_title)
    draw.line([(100, 160), (width - 100, 160)], fill=(0, 0, 0), width=3)

    # Main Details Box
    y = 210
    line_h = 60

    rows = [
        ("SHOP NAME", shop_name or "Smart Print"),
        ("SHOP NUMBER / ID", shop_id or "N/A"),
        ("MOBILE NUMBER", mobile or "N/A"),
        ("CONNECTOR TOKEN", connector_token or "N/A"),
        ("PRINTER", printer_name or "System Default"),
        ("DATE & TIME", datetime.now().strftime("%d-%m-%Y  %I:%M:%S %p"))
    ]

    for label, val in rows:
        draw.text((100, y), f"{label.ljust(20)} :", fill=(0, 0, 0), font=font_label)
        draw.text((460, y), str(val), fill=(0, 0, 0), font=font_val)
        y += line_h

    # Bottom border line
    y += 20
    draw.line([(100, y), (width - 100, y)], fill=(0, 0, 0), width=3)

    y += 30
    draw.text((100, y), "* Enter this Shop Number / ID and Token in SmartPrintConnect App on your PC.", fill=(60, 60, 60), font=font_note)
    
    # The rest of the page (from y=650 down to height=1754) remains 100% BLANK / WHITE.
    img.save(pdf_path, "PDF", resolution=150.0)
    return str(pdf_path)

