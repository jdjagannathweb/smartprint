import os
import socket
import base64
import json
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from pydantic import BaseModel

import database
from services.printer_service import get_installed_printers, print_pdf, generate_test_page_pdf
from services.payment_service import generate_upi_uri, generate_qr_base64, generate_counter_qr
from services.tunnel_service import start_tunnel_thread, get_public_url
from services.document_service import process_uploaded_file, parse_page_range, prepare_final_print_pdf, delete_job_files, cleanup_old_uploads
import threading
import time

def start_file_cleaner_thread():
    def cleaner_loop():
        while True:
            try:
                cleanup_old_uploads(max_age_minutes=15)
            except Exception:
                pass
            time.sleep(300) # Runs every 5 minutes
    t = threading.Thread(target=cleaner_loop, daemon=True)
    t.start()
    return t

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    if not os.environ.get("RENDER"):
        start_tunnel_thread()
    start_file_cleaner_thread()
    yield

app = FastAPI(title="Smart Print Cloud Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
PUBLIC_DIR = BASE_DIR / "public"
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(PUBLIC_DIR)), name="static")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def get_base_url():
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")
    pub = get_public_url()
    if pub:
        return pub
    return f"http://{get_local_ip()}:8000"

def trigger_print_execution(job_id: str):
    job = database.get_job(job_id)
    if not job:
        return
    shop = database.get_shop_by_id(job["shop_id"])
    printer_name = shop.get("selected_printer") if shop else None
    
    database.update_job_status(job_id, {"print_status": "printing", "print_error": None})
    try:
        final_pdf_path = prepare_final_print_pdf(job_id)
        copies = int(job.get("copies", 1))
        color_mode = job.get("color_mode", "bw")
        
        result = print_pdf(
            file_path=final_pdf_path,
            printer_name=printer_name,
            copies=copies,
            color_mode=color_mode
        )
        if result.get("success"):
            database.update_job_status(job_id, {"print_status": "printed", "print_error": None})
        else:
            database.update_job_status(job_id, {"print_status": "failed", "print_error": result.get("error", "Print failed")})
    except Exception as e:
        database.update_job_status(job_id, {"print_status": "failed", "print_error": str(e)})

# ==================== AUTH & REGISTRATION APIS ====================

class RegisterRequest(BaseModel):
    shop_name: str
    owner_name: str
    mobile: str
    password: str
    slug: Optional[str] = None
    upi_id: Optional[str] = None

@app.post("/api/auth/register")
def register_member(body: RegisterRequest):
    res = database.register_shop(
        shop_name=body.shop_name.strip(),
        owner_name=body.owner_name.strip(),
        mobile=body.mobile.strip(),
        password=body.password.strip(),
        slug=body.slug.strip() if body.slug else "",
        upi_id=body.upi_id.strip() if body.upi_id else ""
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return {"success": True, "shop": res}

class LoginRequest(BaseModel):
    mobile: str
    password: str

@app.post("/api/auth/login")
def login_member(body: LoginRequest):
    shop = database.get_shop_by_mobile(body.mobile.strip())
    if not shop or shop["password"] != body.password.strip():
        raise HTTPException(status_code=401, detail="ଭୁଲ୍ ମୋବାଇଲ୍ ନମ୍ବର କିମ୍ବା ପାସୱାର୍ଡ!")
    return {"success": True, "shop": shop}

# ==================== SHOP DASHBOARD APIS ====================

@app.get("/api/shop/{shop_id}")
def get_shop_details(shop_id: str):
    shop = database.get_shop_by_id(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Calculate subscription validity
    shop["days_left"] = database.get_subscription_days_left(shop)
    shop["is_valid"] = database.is_subscription_valid(shop)
    
    # Generate customer portal counter QR code
    base_url = get_base_url()
    customer_url = f"{base_url}/s/{shop['slug']}"
    shop["customer_url"] = customer_url
    shop["counter_qr"] = generate_counter_qr(customer_url)
    
    # Include SaaS 2 plans info for renewal
    saas = database.get_all_saas_settings()
    shop["saas_plans"] = {
        "plan1": {"name": saas.get("plan1_name", "6 Months"), "days": int(saas.get("plan1_days", 180)), "price": float(saas.get("plan1_price", 499))},
        "plan2": {"name": saas.get("plan2_name", "1 Year"), "days": int(saas.get("plan2_days", 365)), "price": float(saas.get("plan2_price", 899))},
        "superadmin_upi_id": saas.get("superadmin_upi_id", "9937037131@ybl"),
        "superadmin_upi_name": saas.get("superadmin_upi_name", "Smart Print Platform")
    }
    return shop

class ShopSettingsUpdate(BaseModel):
    shop_name: str
    owner_name: str
    upi_id: str
    rate_bw: float
    rate_color: float
    selected_printer: str = ""

@app.post("/api/shop/{shop_id}/settings")
def update_shop_config(shop_id: str, body: ShopSettingsUpdate):
    shop = database.get_shop_by_id(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    updated = database.update_shop_settings(shop_id, {
        "shop_name": body.shop_name,
        "owner_name": body.owner_name,
        "upi_id": body.upi_id,
        "rate_bw": body.rate_bw,
        "rate_color": body.rate_color,
        "selected_printer": body.selected_printer
    })
    return {"success": True, "shop": updated}

@app.post("/api/shop/{shop_id}/upload-qr")
async def upload_shop_standee_qr(shop_id: str, file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    b64_img = f"data:{file.content_type or 'image/png'};base64," + base64.b64encode(content).decode("utf-8")
    database.update_shop_settings(shop_id, {"shop_qr_image": b64_img})
    return {"success": True, "shop_qr_image": b64_img}

@app.delete("/api/shop/{shop_id}/remove-qr")
def remove_shop_standee_qr(shop_id: str):
    database.update_shop_settings(shop_id, {"shop_qr_image": ""})
    return {"success": True}

@app.get("/api/shop/{shop_id}/jobs")
def get_shop_orders(shop_id: str):
    jobs = database.get_shop_jobs(shop_id)
    stats = database.get_shop_stats(shop_id)
    return {"jobs": jobs, "stats": stats}

# ==================== CUSTOMER PORTAL APIS (/s/{slug}) ====================

@app.get("/api/customer/shop/{slug}")
def get_customer_shop_info(slug: str):
    shop = database.get_shop_by_slug(slug)
    if not shop:
        raise HTTPException(status_code=404, detail="ଦୋକାନ ମିଳିଲା ନାହିଁ (Shop not found)")
    
    # Check if subscription expired
    is_valid = database.is_subscription_valid(shop)
    
    return {
        "shop_id": shop["shop_id"],
        "slug": shop["slug"],
        "shop_name": shop["shop_name"],
        "owner_name": shop["owner_name"],
        "rate_bw": shop["rate_bw"],
        "rate_color": shop["rate_color"],
        "upi_id": shop["upi_id"],
        "shop_qr_image": shop["shop_qr_image"],
        "is_active": bool(shop["is_active"]),
        "subscription_valid": is_valid
    }

@app.post("/api/customer/upload")
async def customer_upload(shop_id: str = Form(...), file: UploadFile = File(...)):
    shop = database.get_shop_by_id(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    if not database.is_subscription_valid(shop):
        raise HTTPException(status_code=403, detail="ଏହି ଦୋକାନର ସବସ୍କ୍ରିପସନ୍ ସମାପ୍ତ ହୋଇଯାଇଛି। ଦୟାକରି ଦୋକାନୀଙ୍କ ସହ ଯୋଗାଯୋଗ କରନ୍ତୁ।")
    
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    
    job = process_uploaded_file(file.filename, content)
    rate = float(shop.get("rate_bw", 2.0))
    total = rate * job["total_pages"]
    
    upi_uri = generate_upi_uri(
        upi_id=shop.get("upi_id") or "merchant@upi",
        merchant_name=shop.get("shop_name", "Print"),
        amount=total,
        order_id=job["id"]
    )
    qr_b64 = generate_qr_base64(upi_uri)
    
    # Save job in database
    job_record = {
        "id": job["id"],
        "shop_id": shop_id,
        "original_name": file.filename,
        "pdf_path": job["pdf_path"],
        "total_pages": job["total_pages"],
        "num_pages_to_print": job["total_pages"],
        "copies": 1,
        "color_mode": "bw",
        "rate_per_page": rate,
        "total_amount": total,
        "payment_status": "pending",
        "print_status": "queued",
        "created_at": job["created_at"]
    }
    database.create_job(job_record)
    
    return {
        **job_record,
        "job": job_record,
        "upi_uri": upi_uri,
        "qr_code": qr_b64,
        "qr_code_base64": qr_b64,
        "shop_qr_image": shop.get("shop_qr_image", ""),
        "upi_id": shop.get("upi_id", "")
    }

class CustomerConfigureRequest(BaseModel):
    copies: int = 1
    color_mode: str = "bw"
    selected_pages: str = "all"
    page_range: str = None

@app.post("/api/customer/jobs/{job_id}/configure")
def customer_configure_job(job_id: str, body: CustomerConfigureRequest):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    shop = database.get_shop_by_id(job["shop_id"])
    
    rate = float(shop["rate_color"]) if body.color_mode == "color" else float(shop["rate_bw"])
    total_doc_pages = job["total_pages"]
    page_choice = body.page_range or body.selected_pages or "all"
    pages_to_print = parse_page_range(page_choice, total_doc_pages)
    num_pages = len(pages_to_print)
    copies = max(1, body.copies)
    total_amount = round(num_pages * copies * rate, 2)
    
    upi_uri = generate_upi_uri(
        upi_id=shop.get("upi_id") or "merchant@upi",
        merchant_name=shop.get("shop_name", "Print"),
        amount=total_amount,
        order_id=job_id
    )
    qr_b64 = generate_qr_base64(upi_uri)
    
    updated = database.update_job_status(job_id, {
        "num_pages_to_print": num_pages,
        "copies": copies,
        "color_mode": body.color_mode,
        "rate_per_page": rate,
        "total_amount": total_amount
    })
    
    return {
        **updated,
        "job": updated,
        "upi_uri": upi_uri,
        "qr_code": qr_b64,
        "qr_code_base64": qr_b64,
        "shop_qr_image": shop.get("shop_qr_image", ""),
        "upi_id": shop.get("upi_id", "")
    }

@app.get("/api/customer/jobs/{job_id}/status")
def customer_get_status(job_id: str):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/customer/jobs/{job_id}/pay-claimed")
def customer_claim_paid(job_id: str):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    updated = database.update_job_status(job_id, {
        "payment_status": "claimed",
        "print_status": "waiting_merchant"
    })
    return {"success": True, "job": updated}

# ==================== MERCHANT ORDER ACTIONS ====================

@app.post("/api/shop/{shop_id}/jobs/{job_id}/approve")
def merchant_approve_order(shop_id: str, job_id: str, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job or job["shop_id"] != shop_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    updated = database.update_job_status(job_id, {
        "payment_status": "paid",
        "print_status": "printing"
    })
    # Also trigger local print if local printer configured
    background_tasks.add_task(trigger_print_execution, job_id)
    return {"success": True, "job": updated}

@app.post("/api/shop/{shop_id}/jobs/{job_id}/reject")
def merchant_reject_order(shop_id: str, job_id: str):
    job = database.get_job(job_id)
    if not job or job["shop_id"] != shop_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    updated = database.update_job_status(job_id, {
        "payment_status": "rejected",
        "print_status": "cancelled"
    })
    delete_job_files(job_id)
    return {"success": True, "job": updated}

@app.post("/api/shop/{shop_id}/jobs/{job_id}/reprint")
def merchant_reprint_order(shop_id: str, job_id: str, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job or job["shop_id"] != shop_id:
        raise HTTPException(status_code=404, detail="Job not found")
    
    database.update_job_status(job_id, {"print_status": "printing"})
    background_tasks.add_task(trigger_print_execution, job_id)
    return {"success": True, "message": "Reprint triggered"}

@app.delete("/api/shop/{shop_id}/jobs/{job_id}")
def merchant_delete_order(shop_id: str, job_id: str):
    delete_job_files(job_id)
    database.delete_job(job_id, shop_id)
    return {"success": True}

# ==================== OPTION 2: PRINT CONNECTOR AGENT APIS ====================

@app.get("/api/connector/jobs")
def connector_poll_jobs(shop_id: str, token: str):
    shop = database.get_shop_by_id(shop_id)
    if not shop or shop["connector_token"] != token:
        raise HTTPException(status_code=401, detail="Invalid Shop ID or Token")
    
    # Find approved jobs waiting for print
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE shop_id = ? AND payment_status = 'paid' AND print_status = 'printing' ORDER BY created_at ASC", (shop_id,))
    jobs = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"jobs": jobs}

@app.get("/api/connector/download/{job_id}")
def connector_download_pdf(job_id: str, token: str):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    shop = database.get_shop_by_id(job["shop_id"])
    if not shop or shop["connector_token"] != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    pdf_path = prepare_final_print_pdf(job_id)
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{job_id}.pdf")

class ConnectorConfirm(BaseModel):
    token: str
    success: bool
    error: str = None

@app.post("/api/connector/jobs/{job_id}/printed")
def connector_confirm_printed(job_id: str, body: ConnectorConfirm):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    shop = database.get_shop_by_id(job["shop_id"])
    if not shop or shop["connector_token"] != body.token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    status = "printed" if body.success else "failed"
    database.update_job_status(job_id, {"print_status": status, "print_error": body.error})
    if body.success:
        delete_job_files(job_id)
    return {"success": True}

@app.get("/api/connector/script")
def download_connector_python_script():
    return FileResponse(BASE_DIR / "print_connector.py", media_type="text/plain", filename="print_connector.py")

@app.get("/api/connector/download-launcher/{shop_id}")
def download_connector_launcher(shop_id: str):
    shop = database.get_shop_by_id(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    base_url = get_base_url()
    bat_content = f"""@echo off
title Smart Print Connector - {shop['shop_name']}
color 0a
echo ========================================================
echo    SMART PRINT CONNECTOR (OPTION 2 AGENT)
echo    Shop: {shop['shop_name']} ({shop['shop_id']})
echo ========================================================
echo.
echo Checking Python environment...
python --version >nul 2>&1 || (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b
)

if not exist print_connector.py (
    echo Downloading connector agent from cloud server...
    powershell -Command "try {{ [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('{base_url}/api/connector/script', 'print_connector.py'); echo 'Ready!' }} catch {{ echo 'Download error: ' + $_.Exception.Message }}"
)

if not exist connector_config.json (
    echo {{"server_url": "{base_url}", "shop_id": "{shop['shop_id']}", "token": "{shop['connector_token']}"}} > connector_config.json
)

echo Starting Smart Print Connector...
python print_connector.py
pause
"""
    return PlainTextResponse(bat_content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=start_connector_{shop['slug']}.bat"})

@app.get("/api/printers")
def list_printers():
    return {"printers": get_installed_printers()}

class TestPrintRequest(BaseModel):
    printer_name: str = ""

@app.post("/api/test-print")
def run_test_print(body: TestPrintRequest):
    try:
        test_pdf = generate_test_page_pdf()
        res = print_pdf(test_pdf, printer_name=body.printer_name or None, copies=1, color_mode="bw")
        return res
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/network-info")
def get_network_info():
    pub = get_public_url()
    loc = f"http://{get_local_ip()}:8000"
    return {
        "local_url": loc,
        "public_url": pub,
        "base_url": pub or loc,
        "counter_qr": generate_counter_qr(pub or loc),
        "customer_url": pub or loc
    }

# ==================== SUPERADMIN APIS (MASTER CONTROLS) ====================

class SuperAdminLoginRequest(BaseModel):
    pin: str

@app.post("/api/superadmin/login")
def superadmin_auth(body: SuperAdminLoginRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Invalid Super Admin PIN")
    return {"success": True}

@app.get("/api/superadmin/overview")
def superadmin_overview(pin: str):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    overview = database.get_superadmin_overview()
    shops = database.get_all_shops_for_superadmin()
    settings = database.get_all_saas_settings()
    
    return {
        "overview": overview,
        "shops": shops,
        "settings": settings
    }

class ExtendSubscriptionRequest(BaseModel):
    pin: str
    shop_id: str
    days: int

@app.post("/api/superadmin/extend")
def superadmin_extend_sub(body: ExtendSubscriptionRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    new_exp = database.extend_shop_subscription(body.shop_id, body.days)
    return {"success": True, "new_expiry": new_exp}

class ToggleShopRequest(BaseModel):
    pin: str
    shop_id: str

@app.post("/api/superadmin/toggle-shop")
def superadmin_toggle_shop(body: ToggleShopRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    database.toggle_shop_active(body.shop_id)
    return {"success": True}

class UpdatePlansRequest(BaseModel):
    pin: str
    plan1_name: str
    plan1_days: int
    plan1_price: float
    plan2_name: str
    plan2_days: int
    plan2_price: float
    superadmin_upi_id: str
    superadmin_upi_name: str
    free_trial_days: int
    new_master_pin: str = None

@app.post("/api/superadmin/settings")
def superadmin_update_settings(body: UpdatePlansRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    database.set_saas_setting("plan1_name", body.plan1_name)
    database.set_saas_setting("plan1_days", body.plan1_days)
    database.set_saas_setting("plan1_price", body.plan1_price)
    
    database.set_saas_setting("plan2_name", body.plan2_name)
    database.set_saas_setting("plan2_days", body.plan2_days)
    database.set_saas_setting("plan2_price", body.plan2_price)
    
    database.set_saas_setting("superadmin_upi_id", body.superadmin_upi_id)
    database.set_saas_setting("superadmin_upi_name", body.superadmin_upi_name)
    database.set_saas_setting("free_trial_days", body.free_trial_days)
    
    if body.new_master_pin:
        database.set_saas_setting("master_pin", body.new_master_pin)
        
    return {"success": True}

# ==================== HTML PAGE ROUTES ====================

@app.get("/", response_class=HTMLResponse)
def index_page():
    return FileResponse(PUBLIC_DIR / "index.html")

@app.get("/register", response_class=HTMLResponse)
def register_page():
    return FileResponse(PUBLIC_DIR / "register.html")

@app.get("/login", response_class=HTMLResponse)
def login_page():
    return FileResponse(PUBLIC_DIR / "login.html")

@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/admin", response_class=HTMLResponse)
def dashboard_page():
    return FileResponse(PUBLIC_DIR / "dashboard.html")

@app.get("/s/{slug}", response_class=HTMLResponse)
def customer_page(slug: str):
    return FileResponse(PUBLIC_DIR / "customer.html")

@app.get("/superadmin", response_class=HTMLResponse)
def superadmin_page():
    return FileResponse(PUBLIC_DIR / "superadmin.html")

if __name__ == "__main__":
    import uvicorn
    ip = get_local_ip()
    port = int(os.environ.get("PORT", 8000))
    print("=" * 60)
    print(f"  SMART PRINT SAAS PLATFORM STARTED")
    print(f"  Landing & Plans : http://{ip}:{port}")
    print(f"  Shop Register   : http://{ip}:{port}/register")
    print(f"  Shop Dashboard  : http://{ip}:{port}/dashboard")
    print(f"  Master Admin    : http://{ip}:{port}/superadmin")
    print("=" * 60)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
