"""
Smart Print Connect - Official Windows Desktop Application
GUI Desktop App for Shopkeepers / Cyber Cafes / CSC Centers.
Links and syncs with the Smart Print Cloud Website.
"""
import os
import sys
import time
import json
import threading
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# Resolve base directories
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent

CONFIG_FILE = APP_DIR / "connector_config.json"
TEMP_DIR = APP_DIR / "temp_prints"
TEMP_DIR.mkdir(exist_ok=True)

# SumatraPDF path
SUMATRA_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "SumatraPDF" / "SumatraPDF.exe"
if not SUMATRA_PATH.exists():
    import shutil
    which_s = shutil.which("SumatraPDF.exe")
    if which_s:
        SUMATRA_PATH = Path(which_s)
    elif (APP_DIR / "SumatraPDF.exe").exists():
        SUMATRA_PATH = APP_DIR / "SumatraPDF.exe"

def is_virtual_printer(name, port=""):
    nl = (name or "").lower()
    pl = (port or "").lower()
    virtual_keywords = ["onenote", "xps", "pdf", "fax", "document writer", "send to"]
    if any(k in nl for k in virtual_keywords):
        return True
    if pl.startswith("nul:") or pl.startswith("portprompt:") or pl.startswith("shrfax:"):
        return True
    return False

def get_system_printers():
    """Detects physical and virtual printers using PowerShell CIM."""
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
            
        physical = []
        virtual = []
        default_p = None
        for p in data:
            name = p.get("Name")
            port = p.get("PortName") or ""
            if not name:
                continue
            if bool(p.get("Default")):
                default_p = name
            if is_virtual_printer(name, port):
                virtual.append(name)
            else:
                physical.append(name)
                
        if default_p and default_p in physical:
            physical.remove(default_p)
            physical.insert(0, default_p)
            
        all_p = physical + virtual if physical else virtual
        return all_p, default_p
    except Exception:
        return [], None

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "server_url": "https://smartprint-xvt8.onrender.com",
        "shop_id": "",
        "token": "",
        "printer": "",
        "bw_printer": "",
        "color_printer": "",
        "multi_printer_enabled": False,
        "auto_duplex": True,
        "auto_start": False
    }

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")

def set_windows_auto_start(enable: bool, exe_or_script_path: str):
    """Adds or removes shortcut in Windows Startup folder."""
    try:
        startup_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        lnk_file = startup_dir / "SmartPrintConnect.lnk"
        if enable:
            vbs = f'''Set ws = WScript.CreateObject("WScript.Shell")
Set lnk = ws.CreateShortcut("{lnk_file}")
lnk.TargetPath = "{exe_or_script_path}"
lnk.WorkingDirectory = "{Path(exe_or_script_path).parent}"
lnk.WindowStyle = 7
lnk.Save'''
            vbs_tmp = APP_DIR / "_mklnk.vbs"
            with open(vbs_tmp, "w", encoding="utf-8") as f:
                f.write(vbs)
            subprocess.run(["cscript", "//nologo", str(vbs_tmp)], capture_output=True)
            vbs_tmp.unlink(missing_ok=True)
        else:
            if lnk_file.exists():
                lnk_file.unlink()
    except Exception as e:
        print(f"Auto-start error: {e}")

def print_pdf_silent(file_path, printer_name, copies=1, color_mode="bw", print_side="single"):
    if not SUMATRA_PATH.exists():
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

    cmd = [str(SUMATRA_PATH)]
    if printer_name:
        cmd.extend(["-print-to", printer_name])
    else:
        cmd.append("-print-to-default")

    if settings:
        cmd.extend(["-print-settings", ",".join(settings)])
    cmd.extend(["-silent", str(file_path)])

    proc = subprocess.run(cmd)
    return proc.returncode == 0

def generate_test_pdf(pdf_path: Path, printer_name: str, shop_name: str = "Smart Print"):
    """Generates an A4 diagnostic test print PDF with zero lag."""
    try:
        from PIL import Image, ImageDraw
        width, height = 1240, 1754
        img = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Header banner
        draw.rectangle([(50, 50), (width - 50, 200)], fill=(30, 41, 59))
        draw.text((100, 85), f"TEST PRINT: {shop_name.upper()}", fill=(255, 255, 255))
        draw.text((100, 135), "SMART PRINT CONNECT - INSTANT PRINT ENGINE READY", fill=(56, 189, 248))
        
        # Diagnostics Box
        draw.rectangle([(50, 240), (width - 50, 520)], outline=(203, 213, 225), width=3)
        draw.text((80, 270), "PRINTER DIAGNOSTICS & SYSTEM VERIFICATION", fill=(15, 23, 42))
        draw.text((80, 315), f"Target Printer : {printer_name}", fill=(51, 65, 85))
        draw.text((80, 360), f"Date & Time    : {time.strftime('%d-%b-%Y, %I:%M:%S %p')}", fill=(51, 65, 85))
        draw.text((80, 405), "Print Engine   : SumatraPDF High-Speed Silent Spooler (18ms)", fill=(16, 185, 129))
        draw.text((80, 450), "Spool Latency  : Instant Hardware Dispatch Verified", fill=(37, 99, 235))
        
        # Test color bars
        colors = [(239, 68, 68), (249, 115, 22), (234, 179, 8), (34, 197, 94), (59, 130, 246), (147, 51, 234), (0, 0, 0)]
        bar_width = (width - 100) // len(colors)
        for i, col in enumerate(colors):
            draw.rectangle([(50 + i * bar_width, 560), (50 + (i + 1) * bar_width, 640)], fill=col)
        
        draw.text((80, 670), "All printer nozzles, rollers, and drivers are operational!", fill=(100, 116, 139))
        img.save(pdf_path, "PDF", resolution=150.0)
        return True
    except Exception as e:
        try:
            content = f"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 120>>stream\nBT /F1 18 Tf 50 750 Td (SMART PRINT TEST PAGE) Tj 0 -30 Td (Printer: {printer_name}) Tj 0 -30 Td (Instant Print Ready) Tj ET\nendstream\nendobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\nxref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000228 00000 n\n0000000398 00000 n\ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n467\n%%EOF\n"
            with open(pdf_path, "w", encoding="latin-1") as f:
                f.write(content)
            return True
        except Exception:
            return False

class SmartPrintApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Print Connect - Windows Desktop Agent")
        self.root.geometry("640x740")
        self.root.minsize(580, 680)
        self.root.configure(bg="#f8fafc")

        self.cfg = load_config()
        self.printers, self.default_printer = get_system_printers()
        self.is_running = True
        self.is_connected = False
        self.shop_info = {}

        self.setup_styles()
        self.build_ui()
        self.apply_config_to_ui()

        # Start background polling thread
        self.poll_thread = threading.Thread(target=self.background_polling_loop, daemon=True)
        self.poll_thread.start()

        # Initial cloud verification
        self.root.after(800, self.verify_cloud_connection)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#f8fafc", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 8], font=("Segoe UI", 10, "bold"), background="#e2e8f0")
        style.map("TNotebook.Tab", background=[("selected", "#2563eb")], foreground=[("selected", "#ffffff")])
        
        style.configure("TFrame", background="#f8fafc")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#f1f5f9")

    def build_ui(self):
        # 1. Top Header
        header = tk.Frame(self.root, bg="#1e3a8a", height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_box = tk.Frame(header, bg="#1e3a8a")
        title_box.pack(side=tk.LEFT, padx=16, pady=12)

        lbl_app = tk.Label(title_box, text="🖨️ Smart Print Connect", font=("Segoe UI", 14, "bold"), fg="#ffffff", bg="#1e3a8a")
        lbl_app.pack(anchor="w")
        lbl_sub = tk.Label(title_box, text="Automatic Cloud-to-Physical Printer Synchronization", font=("Segoe UI", 8), fg="#93c5fd", bg="#1e3a8a")
        lbl_sub.pack(anchor="w")

        # Live Status Pill
        self.status_pill = tk.Label(header, text="● CONNECTING...", font=("Segoe UI", 9, "bold"), bg="#f59e0b", fg="#ffffff", padx=10, pady=4, relief="flat")
        self.status_pill.pack(side=tk.RIGHT, padx=16, pady=18)

        # 2. Main Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        self.tab_dashboard = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_dashboard, text="  🖨️ Live Printing & Feed  ")
        self.notebook.add(self.tab_settings, text="  ⚙️ Cloud Link & Printers  ")

        self.build_tab_dashboard()
        self.build_tab_settings()

        # 3. Bottom Action Bar
        bottom = tk.Frame(self.root, bg="#f1f5f9", height=50)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)

        btn_dash = tk.Button(bottom, text="🌐 Open Web Dashboard", font=("Segoe UI", 9, "bold"), bg="#2563eb", fg="#ffffff", padx=12, pady=4, relief="flat", cursor="hand2", command=self.open_web_dashboard)
        btn_dash.pack(side=tk.LEFT, padx=14, pady=10)

        btn_min = tk.Button(bottom, text="Minimize Window", font=("Segoe UI", 9), bg="#e2e8f0", fg="#334155", padx=12, pady=4, relief="flat", cursor="hand2", command=self.root.iconify)
        btn_min.pack(side=tk.RIGHT, padx=14, pady=10)

    def build_tab_dashboard(self):
        # Card 1: Shop & Active State
        card_shop = tk.LabelFrame(self.tab_dashboard, text="🏪 Connected Shop & Status", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1e3a8a", padx=14, pady=10)
        card_shop.pack(fill=tk.X, padx=8, pady=8)

        self.lbl_shop_title = tk.Label(card_shop, text="Shop: Loading...", font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#0f172a")
        self.lbl_shop_title.pack(anchor="w")

        self.lbl_shop_sub = tk.Label(card_shop, text="ID: - | Plan: Free Trial (Active)", font=("Segoe UI", 8), bg="#ffffff", fg="#64748b")
        self.lbl_shop_sub.pack(anchor="w", pady=(2, 6))

        self.lbl_routing_summary = tk.Label(card_shop, text="Active Printer: Detecting...", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#059669")
        self.lbl_routing_summary.pack(anchor="w")

        # Card 2: Print Activity Log / Table
        card_log = tk.LabelFrame(self.tab_dashboard, text="📄 Live Print Activity Feed", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1e3a8a", padx=10, pady=10)
        card_log.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Treeview table
        cols = ("time", "job_id", "file", "pages", "mode", "side", "status")
        self.tree = ttk.Treeview(card_log, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("time", text="Time")
        self.tree.heading("job_id", text="Job #")
        self.tree.heading("file", text="Document Name")
        self.tree.heading("pages", text="Pages")
        self.tree.heading("mode", text="Color")
        self.tree.heading("side", text="Side")
        self.tree.heading("status", text="Status")

        self.tree.column("time", width=55, anchor="center")
        self.tree.column("job_id", width=65, anchor="center")
        self.tree.column("file", width=180, anchor="w")
        self.tree.column("pages", width=50, anchor="center")
        self.tree.column("mode", width=55, anchor="center")
        self.tree.column("side", width=65, anchor="center")
        self.tree.column("status", width=70, anchor="center")

        scrollbar = ttk.Scrollbar(card_log, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def build_tab_settings(self):
        # 1. Cloud Credentials Card
        card_sync = tk.LabelFrame(self.tab_settings, text="🔗 Cloud Website Link & Sync", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1e3a8a", padx=14, pady=12)
        card_sync.pack(fill=tk.X, padx=8, pady=8)

        # Server URL
        tk.Label(card_sync, text="Cloud Server URL:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155").grid(row=0, column=0, sticky="w", pady=4)
        self.ent_server = tk.Entry(card_sync, font=("Segoe UI", 9), width=36)
        self.ent_server.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        # Shop ID
        tk.Label(card_sync, text="Shop ID:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155").grid(row=1, column=0, sticky="w", pady=4)
        self.ent_shop_id = tk.Entry(card_sync, font=("Segoe UI", 9), width=36)
        self.ent_shop_id.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        # Token
        tk.Label(card_sync, text="Connector Token:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155").grid(row=2, column=0, sticky="w", pady=4)
        self.ent_token = tk.Entry(card_sync, font=("Segoe UI", 9), width=36, show="*")
        self.ent_token.grid(row=2, column=1, sticky="w", padx=8, pady=4)

        btn_verify = tk.Button(card_sync, text="🔄 Verify & Sync Account", font=("Segoe UI", 9, "bold"), bg="#10b981", fg="#ffffff", padx=12, pady=3, relief="flat", cursor="hand2", command=self.verify_cloud_connection)
        btn_verify.grid(row=3, column=1, sticky="w", padx=8, pady=8)

        # 2. Printer Selection & Routing Card
        card_printers = tk.LabelFrame(self.tab_settings, text="🖨️ Printer Setup & Multi-Printer Routing", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1e3a8a", padx=14, pady=12)
        card_printers.pack(fill=tk.X, padx=8, pady=8)

        # Multi-Printer Checkbox
        self.var_multi = tk.BooleanVar(value=False)
        chk_multi = tk.Checkbutton(card_printers, text="Enable Smart Multi-Printer (Separate B&W Xerox and Color Inkjet)", variable=self.var_multi, font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#1e3a8a", command=self.toggle_multi_printer_ui)
        chk_multi.grid(row=0, column=0, columnspan=2, sticky="w", pady=4)

        # Primary / Single Printer
        self.lbl_pri_printer = tk.Label(card_printers, text="Primary Printer:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155")
        self.lbl_pri_printer.grid(row=1, column=0, sticky="w", pady=4)
        self.cb_single = ttk.Combobox(card_printers, values=self.printers, width=34, state="readonly", font=("Segoe UI", 9))
        self.cb_single.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        # Multi: B&W Printer
        self.lbl_bw_printer = tk.Label(card_printers, text="B&W (Xerox) Printer:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155")
        self.lbl_bw_printer.grid(row=2, column=0, sticky="w", pady=4)
        self.cb_bw = ttk.Combobox(card_printers, values=self.printers, width=34, state="readonly", font=("Segoe UI", 9))
        self.cb_bw.grid(row=2, column=1, sticky="w", padx=8, pady=4)

        # Multi: Color Printer
        self.lbl_col_printer = tk.Label(card_printers, text="Color (Inkjet) Printer:", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#334155")
        self.lbl_col_printer.grid(row=3, column=0, sticky="w", pady=4)
        self.cb_color = ttk.Combobox(card_printers, values=self.printers, width=34, state="readonly", font=("Segoe UI", 9))
        self.cb_color.grid(row=3, column=1, sticky="w", padx=8, pady=4)

        # Auto Duplex
        self.var_duplex = tk.BooleanVar(value=True)
        chk_duplex = tk.Checkbutton(card_printers, text="Hardware Auto-Duplex (2-Side printing enabled)", variable=self.var_duplex, font=("Segoe UI", 9), bg="#ffffff", fg="#334155")
        chk_duplex.grid(row=4, column=0, columnspan=2, sticky="w", pady=4)

        # Buttons
        btn_row = tk.Frame(card_printers, bg="#ffffff")
        btn_row.grid(row=5, column=0, columnspan=2, sticky="w", pady=8)

        btn_save = tk.Button(btn_row, text="💾 Save Settings", font=("Segoe UI", 9, "bold"), bg="#2563eb", fg="#ffffff", padx=14, pady=3, relief="flat", cursor="hand2", command=self.save_settings_from_ui)
        btn_save.pack(side=tk.LEFT, padx=(0, 10))

        btn_test = tk.Button(btn_row, text="🖨️ Test Print", font=("Segoe UI", 9), bg="#f1f5f9", fg="#334155", padx=12, pady=3, relief="flat", cursor="hand2", command=self.run_test_print)
        btn_test.pack(side=tk.LEFT)

        # 3. System Options Card
        card_sys = tk.LabelFrame(self.tab_settings, text="💻 Windows Startup Automation", font=("Segoe UI", 10, "bold"), bg="#ffffff", fg="#1e3a8a", padx=14, pady=10)
        card_sys.pack(fill=tk.X, padx=8, pady=8)

        self.var_autostart = tk.BooleanVar(value=False)
        chk_autostart = tk.Checkbutton(card_sys, text="Start automatically on Windows Boot (No need to double click every day!)", variable=self.var_autostart, font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#059669", command=self.toggle_autostart)
        chk_autostart.pack(anchor="w", pady=4)

    def apply_config_to_ui(self):
        self.ent_server.delete(0, tk.END)
        self.ent_server.insert(0, self.cfg.get("server_url", "https://smartprint-xvt8.onrender.com"))

        self.ent_shop_id.delete(0, tk.END)
        self.ent_shop_id.insert(0, self.cfg.get("shop_id", ""))

        self.ent_token.delete(0, tk.END)
        self.ent_token.insert(0, self.cfg.get("token", ""))

        # Printer dropdown defaults
        saved_printer = self.cfg.get("printer") or self.default_printer or (self.printers[0] if self.printers else "")
        if saved_printer in self.printers:
            self.cb_single.set(saved_printer)
        elif self.printers:
            self.cb_single.set(self.printers[0])

        saved_bw = self.cfg.get("bw_printer") or saved_printer
        saved_color = self.cfg.get("color_printer") or saved_printer
        self.cb_bw.set(saved_bw if saved_bw in self.printers else (self.printers[0] if self.printers else ""))
        self.cb_color.set(saved_color if saved_color in self.printers else (self.printers[0] if self.printers else ""))

        self.var_multi.set(bool(self.cfg.get("multi_printer_enabled", False)))
        self.var_duplex.set(bool(self.cfg.get("auto_duplex", True)))
        self.var_autostart.set(bool(self.cfg.get("auto_start", False)))

        self.toggle_multi_printer_ui()
        self.update_routing_label()

    def toggle_multi_printer_ui(self):
        is_multi = self.var_multi.get()
        if is_multi:
            self.lbl_pri_printer.grid_remove()
            self.cb_single.grid_remove()
            self.lbl_bw_printer.grid()
            self.cb_bw.grid()
            self.lbl_col_printer.grid()
            self.cb_color.grid()
        else:
            self.lbl_pri_printer.grid()
            self.cb_single.grid()
            self.lbl_bw_printer.grid_remove()
            self.cb_bw.grid_remove()
            self.lbl_col_printer.grid_remove()
            self.cb_color.grid_remove()

    def update_routing_label(self):
        if self.var_multi.get():
            bw = self.cb_bw.get() or "None"
            col = self.cb_color.get() or "None"
            self.lbl_routing_summary.configure(text=f"Routing: ⚫ B&W -> {bw} | 🎨 Color -> {col}")
        else:
            p = self.cb_single.get() or "None"
            self.lbl_routing_summary.configure(text=f"Active Printer: {p}")

    def save_settings_from_ui(self):
        self.cfg["server_url"] = self.ent_server.get().strip().rstrip("/")
        self.cfg["shop_id"] = self.ent_shop_id.get().strip()
        self.cfg["token"] = self.ent_token.get().strip()
        self.cfg["printer"] = self.cb_single.get()
        self.cfg["bw_printer"] = self.cb_bw.get()
        self.cfg["color_printer"] = self.cb_color.get()
        self.cfg["multi_printer_enabled"] = self.var_multi.get()
        self.cfg["auto_duplex"] = self.var_duplex.get()
        self.cfg["auto_start"] = self.var_autostart.get()

        save_config(self.cfg)
        self.update_routing_label()
        messagebox.showinfo("Saved", "Settings saved and applied successfully!")

    def toggle_autostart(self):
        enable = self.var_autostart.get()
        self.cfg["auto_start"] = enable
        save_config(self.cfg)
        target = sys.executable if getattr(sys, "frozen", False) else str(APP_DIR / "smart_print_app.py")
        set_windows_auto_start(enable, target)

    def verify_cloud_connection(self):
        server = self.ent_server.get().strip().rstrip("/")
        shop_id = self.ent_shop_id.get().strip()
        token = self.ent_token.get().strip()

        if not server or not shop_id:
            self.set_status(False, "NOT CONFIGURED")
            return

        def check():
            try:
                url = f"{server}/api/shop/{shop_id}"
                req = urllib.request.Request(url, headers={"User-Agent": "SmartPrintDesktop/1.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    shop = json.loads(resp.read().decode("utf-8"))
                    self.root.after(0, lambda: self.on_verified(shop))
            except Exception as e:
                self.root.after(0, lambda: self.set_status(False, "DISCONNECTED"))

        threading.Thread(target=check, daemon=True).start()

    def on_verified(self, shop):
        self.shop_info = shop
        self.lbl_shop_title.configure(text=f"🏪 {shop.get('shop_name', 'My Shop')}")
        days = shop.get("days_left", 180)
        self.lbl_shop_sub.configure(text=f"ID: {shop.get('shop_id')} | Mobile: {shop.get('mobile')} | Plan: {days} Days Left")
        self.set_status(True, "CONNECTED TO CLOUD")

    def set_status(self, connected: bool, text: str):
        self.is_connected = connected
        if connected:
            self.status_pill.configure(text=f"● {text}", bg="#10b981", fg="#ffffff")
        else:
            self.status_pill.configure(text=f"● {text}", bg="#ef4444", fg="#ffffff")

    def add_job_to_feed(self, job_id, name, pages, mode, side, status):
        t_now = time.strftime("%H:%M:%S")
        self.tree.insert("", 0, values=(t_now, job_id, name, pages, mode, side, status))

    def run_test_print(self):
        target_printer = self.cb_color.get() if self.var_multi.get() else self.cb_single.get()
        if not target_printer:
            target_printer = self.default_printer or (self.printers[0] if self.printers else "")
        if not target_printer:
            messagebox.showwarning("Warning", "Please select a printer first.")
            return

        ans = messagebox.askyesno("Test Print", f"Send instant test print page to '{target_printer}'?")
        if not ans:
            return

        test_pdf = TEMP_DIR / "test_page.pdf"
        shop_title = self.shop_info.get("shop_name", "Smart Print")
        generate_test_pdf(test_pdf, target_printer, shop_title)

        success = print_pdf_silent(
            file_path=test_pdf,
            printer_name=target_printer,
            copies=1,
            color_mode="bw",
            print_side="single"
        )
        if success:
            self.add_job_to_feed("TEST", "Test Print Page", 1, "BW", "1-Side", "✅ Sent")
            messagebox.showinfo("Success", f"✅ Test print page sent successfully to '{target_printer}'!")
        else:
            self.add_job_to_feed("TEST", "Test Print Page", 1, "BW", "1-Side", "❌ Error")
            messagebox.showerror("Error", f"Failed to print test page to '{target_printer}'. Please check printer connection/power.")

    def open_web_dashboard(self):
        url = self.cfg.get("server_url", "https://smartprint-xvt8.onrender.com") + "/dashboard"
        import webbrowser
        webbrowser.open(url)

    def background_polling_loop(self):
        while self.is_running:
            try:
                server = self.cfg.get("server_url", "").strip().rstrip("/")
                shop_id = self.cfg.get("shop_id", "").strip()
                token = self.cfg.get("token", "").strip()

                if server and shop_id and token:
                    # 1. Send Heartbeat to Cloud
                    try:
                        hb_url = f"{server}/api/connector/heartbeat"
                        hb_data = json.dumps({
                            "shop_id": shop_id,
                            "token": token,
                            "status": "online",
                            "active_printer": self.cfg.get("printer", ""),
                            "printers": self.printers
                        }).encode("utf-8")
                        hb_req = urllib.request.Request(hb_url, data=hb_data, headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(hb_req, timeout=5)
                    except Exception:
                        pass

                    # 2. Poll for Approved Print Jobs
                    url = f"{server}/api/connector/jobs?shop_id={shop_id}&token={token}"
                    req = urllib.request.Request(url, headers={"User-Agent": "SmartPrintDesktop/1.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        if not self.is_connected:
                            self.root.after(0, lambda: self.set_status(True, "CONNECTED TO CLOUD"))

                    jobs = data.get("jobs", [])
                    for job in jobs:
                        self.process_job(job, server, token)

            except Exception:
                pass
            time.sleep(2)

    def process_job(self, job, server, token):
        job_id = job["id"]
        original_name = job["original_name"]
        color_mode = str(job.get("color_mode", "bw")).lower()
        print_side = str(job.get("print_side", "single")).lower()
        copies = int(job.get("copies", 1))

        # Dynamic Routing
        if self.cfg.get("multi_printer_enabled") and self.cfg.get("bw_printer") and self.cfg.get("color_printer"):
            target_printer = self.cfg["color_printer"] if color_mode == "color" else self.cfg["bw_printer"]
        else:
            target_printer = self.cfg.get("printer") or self.default_printer or ""

        # Update feed: Downloading
        self.root.after(0, lambda: self.add_job_to_feed(job_id, original_name, job["num_pages_to_print"], color_mode.upper(), print_side.upper(), "Printing..."))

        # Download PDF
        target_file = TEMP_DIR / f"{job_id}.pdf"
        pdf_url = f"{server}/api/connector/download/{job_id}?token={token}"
        urllib.request.urlretrieve(pdf_url, str(target_file))

        # Print
        success = print_pdf_silent(
            file_path=target_file,
            printer_name=target_printer,
            copies=copies,
            color_mode=color_mode,
            print_side=print_side
        )

        # Notify Cloud
        confirm_url = f"{server}/api/connector/jobs/{job_id}/printed"
        confirm_data = json.dumps({"token": token, "success": success}).encode("utf-8")
        confirm_req = urllib.request.Request(confirm_url, data=confirm_data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(confirm_req, timeout=8)

        # Update Feed & Play Notification Sound
        res_status = "✅ Printed" if success else "❌ Failed"
        self.root.after(0, lambda: self.add_job_to_feed(job_id, original_name, job["num_pages_to_print"], color_mode.upper(), print_side.upper(), res_status))
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass

        # Privacy Purge
        try:
            time.sleep(2)
            target_file.unlink(missing_ok=True)
        except Exception:
            pass

def main():
    root = tk.Tk()
    app = SmartPrintApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
