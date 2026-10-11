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

def generate_test_page_pdf(printer_name: str = "System Default", shop_name: str = "Smart Print", output_path: str = None) -> str:
    """Generates an A4 test print PDF."""
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
    
    # Draw header banner
    draw.rectangle([(50, 50), (width - 50, 200)], fill=(30, 41, 59))
    draw.text((100, 90), f"TEST PRINT: {shop_name.upper()}", fill=(255, 255, 255))
    draw.text((100, 140), "AUTO-PRINT & UPI PAYMENT SYSTEM READY", fill=(56, 189, 248))
    
    # Draw printer details box
    draw.rectangle([(50, 240), (width - 50, 500)], outline=(203, 213, 225), width=3)
    draw.text((80, 270), "PRINTER DIAGNOSTICS & VERIFICATION", fill=(15, 23, 42))
    draw.text((80, 320), f"Target Printer : {printer_name or 'System Default'}", fill=(51, 65, 85))
    draw.text((80, 370), f"Generated On   : {datetime.now().strftime('%d %B %Y, %I:%M:%S %p')}", fill=(51, 65, 85))
    draw.text((80, 420), "Print Engine   : SumatraPDF Silent Windows Dispatcher", fill=(16, 185, 129))
    
    # Draw test color bars
    colors = [(239, 68, 68), (249, 115, 22), (234, 179, 8), (34, 197, 94), (59, 130, 246), (147, 51, 234), (0, 0, 0)]
    bar_width = (width - 100) // len(colors)
    for i, col in enumerate(colors):
        x1 = 50 + (i * bar_width)
        x2 = x1 + bar_width
        draw.rectangle([(x1, 550), (x2, 630)], fill=col)
    
    draw.text((80, 660), "All printer nozzles and drivers are operational!", fill=(100, 116, 139))
    
    img.save(pdf_path, "PDF", resolution=150.0)
    return str(pdf_path)
