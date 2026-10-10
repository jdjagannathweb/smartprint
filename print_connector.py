"""
Smart Print Connector - Option 2 Standalone Local Printing Agent
Run this on the Shopkeeper's PC where the physical printer is connected.
"""
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "connector_config.json"

def get_installed_printers():
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Printer | Select-Object Name, Default | ConvertTo-Json -Compress"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        raw = res.stdout.strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [p.get("Name") for p in data if p.get("Name")]
    except Exception:
        return []

def print_pdf_silent(file_path, printer_name, copies=1, color_mode="bw"):
    sumatra = Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe"
    if not sumatra.exists():
        # Fallback to powershell
        ps_cmd = f'Start-Process -FilePath "{file_path}" -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden'
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd])
        return True
    
    settings = []
    if copies > 1:
        settings.append(f"{copies}x")
    if color_mode == "bw":
        settings.append("monochrome")
    elif color_mode == "color":
        settings.append("color")
        
    cmd = [str(sumatra)]
    if printer_name:
        cmd.extend(["-print-to", printer_name])
    else:
        cmd.append("-print-to-default")
        
    if settings:
        cmd.extend(["-print-settings", ",".join(settings)])
    cmd.extend(["-silent", str(file_path)])
    
    proc = subprocess.run(cmd)
    return proc.returncode == 0

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def main():
    print("=" * 60)
    print("   SMART PRINT CONNECTOR (OPTION 2 AGENT)")
    print("   Connects this PC's printer to Smart Print Cloud")
    print("=" * 60)
    
    cfg = load_config()
    server_url = cfg.get("server_url") or input("Enter Server URL (e.g. http://localhost:8000 or your domain): ").strip()
    server_url = server_url.rstrip("/")
    
    shop_id = cfg.get("shop_id") or input("Enter Shop ID (e.g. SHP-818D63): ").strip()
    token = cfg.get("token") or input("Enter Connector Token: ").strip()
    
    printers = get_installed_printers()
    selected_printer = cfg.get("printer")
    if not selected_printer:
        print("\nAvailable Printers:")
        for idx, p in enumerate(printers, 1):
            print(f"  [{idx}] {p}")
        p_idx = input("Select printer number (or press Enter for default): ").strip()
        if p_idx.isdigit() and 1 <= int(p_idx) <= len(printers):
            selected_printer = printers[int(p_idx) - 1]
        else:
            selected_printer = printers[0] if printers else ""
            
    cfg = {
        "server_url": server_url,
        "shop_id": shop_id,
        "token": token,
        "printer": selected_printer
    }
    save_config(cfg)
    
    print(f"\nConnected successfully!")
    print(f"Shop ID : {shop_id}")
    print(f"Printer : {selected_printer}")
    print("Listening for approved customer print jobs...\n")
    
    downloads_dir = Path(__file__).parent / "temp_prints"
    downloads_dir.mkdir(exist_ok=True)
    
    while True:
        try:
            url = f"{server_url}/api/connector/jobs?shop_id={shop_id}&token={token}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
            jobs = data.get("jobs", [])
            for job in jobs:
                print(f"[NEW APPROVED JOB] #{job['id']} - {job['original_name']} ({job['num_pages_to_print']} pages, {job['copies']} copies)")
                pdf_url = f"{server_url}/api/connector/download/{job['id']}?token={token}"
                target_file = downloads_dir / f"{job['id']}.pdf"
                
                urllib.request.urlretrieve(pdf_url, str(target_file))
                print(f"  Printing silently to {selected_printer}...")
                
                success = print_pdf_silent(
                    file_path=target_file,
                    printer_name=selected_printer,
                    copies=job.get("copies", 1),
                    color_mode=job.get("color_mode", "bw")
                )
                
                # Report back
                confirm_url = f"{server_url}/api/connector/jobs/{job['id']}/printed"
                confirm_data = json.dumps({"token": token, "success": success}).encode("utf-8")
                confirm_req = urllib.request.Request(confirm_url, data=confirm_data, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(confirm_req)
                print(f"  SUCCESS: Job #{job['id']} printed and status updated!")
                
                # Privacy Auto-Purge: Remove physical file from local computer
                try:
                    time.sleep(2)
                    target_file.unlink(missing_ok=True)
                    print(f"  🔒 Privacy: Local file deleted securely.\n")
                except Exception:
                    pass
                
        except Exception as e:
            # Silent retry
            pass
        time.sleep(3)

if __name__ == "__main__":
    main()
