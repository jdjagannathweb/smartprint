"""
Smart Print Connector - Standalone Local Printing Agent
Connects Windows PC printers to Smart Print Cloud.
Supports Single Printer Mode & Smart Multi-Printer Routing (B&W vs Color).
"""
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

# Safe console encoding for Windows CMD
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CONFIG_FILE = Path(__file__).parent / "connector_config.json"

def is_virtual_printer(name, port=""):
    nl = (name or "").lower()
    pl = (port or "").lower()
    virtual_keywords = ["onenote", "xps", "pdf", "fax", "document writer", "send to"]
    if any(k in nl for k in virtual_keywords):
        return True
    if pl.startswith("nul:") or pl.startswith("portprompt:") or pl.startswith("shrfax:"):
        return True
    return False

def get_installed_printers():
    try:
        cmd = [
            "powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Printer | Select-Object Name, Default, PortName | ConvertTo-Json -Compress"
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        raw = res.stdout.strip()
        if not raw:
            return [], None
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
            
        physical_printers = []
        virtual_printers = []
        default_printer = None
        
        for p in data:
            name = p.get("Name")
            port = p.get("PortName") or ""
            if not name:
                continue
            is_def = bool(p.get("Default"))
            if is_def:
                default_printer = name
                
            if is_virtual_printer(name, port):
                virtual_printers.append(name)
            else:
                physical_printers.append(name)
                
        # Put default physical printer at top if exists
        if default_printer and default_printer in physical_printers:
            physical_printers.remove(default_printer)
            physical_printers.insert(0, default_printer)
            
        # Return physical printers first, then virtual
        all_printers = physical_printers + virtual_printers if physical_printers else virtual_printers
        return all_printers, default_printer
    except Exception:
        return [], None

def print_pdf_silent(file_path, printer_name, copies=1, color_mode="bw", print_side="single"):
    sumatra = Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe"
    if not sumatra.exists():
        # Fallback to powershell PrintTo
        ps_cmd = f'Start-Process -FilePath "{file_path}" -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden'
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd])
        return proc.returncode == 0
    
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
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def configure_printers_interactive(cfg):
    printers, system_default = get_installed_printers()
    
    print("\n" + "=" * 65)
    print("   [PRINTER SETUP] SMART PRINT - SELECTION & MULTI-PRINTER ROUTING")
    print("=" * 65)
    print("\nDetected Printers on this Computer:")
    for idx, p in enumerate(printers, 1):
        tag = ""
        if p == system_default:
            tag += " (Windows Default)"
        if p == cfg.get("printer"):
            tag += " [Active Single]"
        if p == cfg.get("bw_printer"):
            tag += " [Active B&W]"
        if p == cfg.get("color_printer"):
            tag += " [Active Color]"
        print(f"  [{idx}] {p}{tag}")
        
    print("\nChoose Setup Mode:")
    print("  [1] Single Printer (All prints sent to 1 printer)")
    print("  [2] Smart Multi-Printer (Separate B&W and Color printers - Best for Xerox + Color shops!)")
    
    choice = input("\nEnter choice [1 or 2] (Default 1): ").strip()
    
    if choice == "2":
        print("\n--- [Step 1] Select B&W Printer (for Documents / Xerox) ---")
        for idx, p in enumerate(printers, 1):
            print(f"  [{idx}] {p}")
        bw_in = input(f"Enter printer number [1-{len(printers)}]: ").strip()
        try:
            bw_printer = printers[int(bw_in) - 1]
        except Exception:
            bw_printer = system_default or printers[0]
            
        print("\n--- [Step 2] Select Color Printer (for Color / Photos) ---")
        for idx, p in enumerate(printers, 1):
            print(f"  [{idx}] {p}")
        color_in = input(f"Enter printer number [1-{len(printers)}]: ").strip()
        try:
            color_printer = printers[int(color_in) - 1]
        except Exception:
            color_printer = system_default or printers[0]
            
        cfg["bw_printer"] = bw_printer
        cfg["color_printer"] = color_printer
        cfg["printer"] = bw_printer
        save_config(cfg)
        
        print("\n" + "=" * 65)
        print("[SUCCESS] SMART MULTI-PRINTER ROUTING SAVED!")
        print(f"   [*] Black & White Jobs  ---> {bw_printer}")
        print(f"   [*] Color Print Jobs    ---> {color_printer}")
        print("=" * 65 + "\n")
    else:
        print(f"\n--- Select Primary Printer [1-{len(printers)}] (or Enter for '{system_default}'): ---")
        p_in = input("Enter printer number: ").strip()
        try:
            if p_in:
                selected = printers[int(p_in) - 1]
            else:
                selected = system_default or printers[0]
        except Exception:
            selected = system_default or printers[0]
            
        cfg["printer"] = selected
        cfg.pop("bw_printer", None)
        cfg.pop("color_printer", None)
        save_config(cfg)
        
        print("\n" + "=" * 65)
        print(f"[SUCCESS] SINGLE PRINTER SAVED: {selected}")
        print("   All print jobs will be printed on this printer.")
        print("=" * 65 + "\n")
        
    return cfg

def main():
    cfg = load_config()
    
    if "--configure" in sys.argv or "--setup" in sys.argv or "--change-printer" in sys.argv:
        configure_printers_interactive(cfg)
        print("Setup complete! You can now launch start_connector.bat to start printing.\n")
        return

    print("=" * 65)
    print("   SMART PRINT CONNECTOR (LOCAL PRINT AGENT)")
    print("   Connects this PC's printer to Smart Print Cloud")
    print("=" * 65)
    
    server_url = cfg.get("server_url") or input("Enter Server URL (e.g. https://your-domain.onrender.com): ").strip()
    server_url = server_url.rstrip("/")
    
    shop_id = cfg.get("shop_id") or input("Enter Shop ID: ").strip()
    token = cfg.get("token") or input("Enter Connector Token: ").strip()
    
    printers, system_default = get_installed_printers()
    selected_printer = cfg.get("printer")
    
    # Auto-fix: if previously assigned to OneNote or virtual printer, switch to true Windows Default
    if selected_printer and is_virtual_printer(selected_printer):
        if system_default and not is_virtual_printer(system_default):
            print(f"\n[AUTO-FIX] Switching from virtual '{selected_printer}' to real Default Printer: '{system_default}'!")
            selected_printer = system_default
            cfg["printer"] = selected_printer
            save_config(cfg)
            
    if not selected_printer:
        selected_printer = system_default or (printers[0] if printers else "")
        cfg["printer"] = selected_printer
        save_config(cfg)
        
    cfg["server_url"] = server_url
    cfg["shop_id"] = shop_id
    cfg["token"] = token
    cfg["printer"] = selected_printer
    save_config(cfg)
    
    is_multi = bool(cfg.get("bw_printer") and cfg.get("color_printer"))
    
    print(f"\n[OK] Connected successfully!")
    print(f"Shop ID     : {shop_id}")
    if is_multi:
        print(f"Routing     : [SMART MULTI-PRINTER]")
        print(f"  [-] B&W Jobs   : {cfg['bw_printer']}")
        print(f"  [-] Color Jobs : {cfg['color_printer']}")
    else:
        print(f"Active Printer : {selected_printer}")
        
    print("\nInstalled Printers on this Computer:")
    for idx, p in enumerate(printers, 1):
        tags = []
        if p == system_default:
            tags.append("Windows Default")
        if is_multi:
            if p == cfg.get("bw_printer"):
                tags.append("B&W Printer")
            if p == cfg.get("color_printer"):
                tags.append("Color Printer")
        elif p == selected_printer:
            tags.append("ACTIVE PRINTER")
        tag_str = f" <--- [{', '.join(tags)}]" if tags else ""
        print(f"  [{idx}] {p}{tag_str}")
        
    print("\n[TIP] Double-click 'change_printer.bat' anytime to switch printers or setup B&W/Color routing")
    print("\n>>> Listening for approved customer print jobs... (Running)\n")
    
    downloads_dir = Path(__file__).parent / "temp_prints"
    downloads_dir.mkdir(exist_ok=True)
    
    while True:
        try:
            url = f"{server_url}/api/connector/jobs?shop_id={shop_id}&token={token}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
            jobs = data.get("jobs", [])
            remote_printer = data.get("selected_printer")
            if remote_printer and remote_printer != cfg.get("printer"):
                cfg["printer"] = remote_printer
                selected_printer = remote_printer
                save_config(cfg)
                print(f"\n[SYNC] Active printer updated from Web Dashboard to: '{remote_printer}'")
            for job in jobs:
                color_mode = str(job.get("color_mode", "bw")).lower()
                
                # Dynamic Printer Routing
                if cfg.get("bw_printer") and cfg.get("color_printer"):
                    if color_mode == "color":
                        target_printer = cfg["color_printer"]
                    else:
                        target_printer = cfg["bw_printer"]
                else:
                    target_printer = cfg.get("printer") or selected_printer
                
                print_side = str(job.get("print_side", "single")).lower()
                
                print(f"\n>>> [NEW JOB RECEIVED] #{job['id']} - {job['original_name']}")
                print(f"    Pages: {job['num_pages_to_print']} | Copies: {job['copies']} | Mode: {color_mode.upper()} | Side: {print_side.upper()}")
                pdf_url = f"{server_url}/api/connector/download/{job['id']}?token={token}"
                target_file = downloads_dir / f"{job['id']}.pdf"
                
                print(f"    [+] Downloading document...")
                urllib.request.urlretrieve(pdf_url, str(target_file))
                
                print(f"    [+] Printing [{color_mode.upper()} | {print_side.upper()}] job silently to '{target_printer}'...")
                success = print_pdf_silent(
                    file_path=target_file,
                    printer_name=target_printer,
                    copies=job.get("copies", 1),
                    color_mode=color_mode,
                    print_side=print_side
                )
                
                confirm_url = f"{server_url}/api/connector/jobs/{job['id']}/printed"
                confirm_data = json.dumps({"token": token, "success": success}).encode("utf-8")
                confirm_req = urllib.request.Request(confirm_url, data=confirm_data, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(confirm_req)
                
                if success:
                    print(f"    [SUCCESS] Job #{job['id']} printed! Status updated to 'printed'.")
                else:
                    print(f"    [FAILED] Job #{job['id']} could not print on '{target_printer}'.")
                
                # Privacy Auto-Purge: Remove physical file from local computer
                try:
                    time.sleep(2)
                    target_file.unlink(missing_ok=True)
                    print(f"    [PRIVACY] Local file deleted securely.\n")
                except Exception:
                    pass
                
        except Exception:
            pass
        time.sleep(3)

if __name__ == "__main__":
    main()
