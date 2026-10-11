import os
import sys
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
from datetime import datetime
from pydantic import BaseModel

import database
from services.printer_service import get_installed_printers, print_pdf, generate_test_page_pdf, SUMATRA_PATH
from services.payment_service import (
    generate_upi_uri, generate_paytm_upi_uri, check_paytm_order_status,
    initiate_phonepe_checkout, check_phonepe_order_status,
    create_smbupi_order, check_smbupi_order_status,
    generate_qr_base64, generate_counter_qr
)
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
    
    # If running on cloud (Render / Linux), the cloud container has no physical printer attached!
    # Leave print_status = 'printing' so the shopkeeper's PC connector agent downloads and prints it!
    if os.environ.get("RENDER") or sys.platform != "win32":
        return
    
    try:
        final_pdf_path = prepare_final_print_pdf(job_id)
        copies = int(job.get("copies", 1))
        color_mode = job.get("color_mode", "bw")
        print_side = job.get("print_side", "single")
        
        result = print_pdf(
            file_path=final_pdf_path,
            printer_name=printer_name,
            copies=copies,
            color_mode=color_mode,
            print_side=print_side
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
    rate_double_bw: Optional[float] = 3.0
    rate_double_color: Optional[float] = 15.0
    selected_printer: str = ""
    auto_print_enabled: Optional[int] = 1
    paytm_mid: Optional[str] = None
    paytm_merchant_key: Optional[str] = None
    paytm_vpa: Optional[str] = None
    paytm_enabled: Optional[int] = None
    phonepe_client_id: Optional[str] = None
    phonepe_client_secret: Optional[str] = None
    phonepe_client_version: Optional[int] = None
    phonepe_env: Optional[str] = None
    phonepe_enabled: Optional[int] = None
    smbupi_api_key: Optional[str] = None
    smbupi_api_secret: Optional[str] = None
    smbupi_webhook_secret: Optional[str] = None
    smbupi_enabled: Optional[int] = None

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
        "rate_double_bw": body.rate_double_bw if body.rate_double_bw is not None else shop.get("rate_double_bw", 3.0),
        "rate_double_color": body.rate_double_color if body.rate_double_color is not None else shop.get("rate_double_color", 15.0),
        "selected_printer": body.selected_printer if body.selected_printer is not None else shop.get("selected_printer", ""),
        "auto_print_enabled": body.auto_print_enabled if body.auto_print_enabled is not None else shop.get("auto_print_enabled", 1),
        "paytm_mid": (body.paytm_mid if body.paytm_mid is not None else shop.get("paytm_mid", "")).strip(),
        "paytm_merchant_key": (body.paytm_merchant_key if body.paytm_merchant_key is not None else shop.get("paytm_merchant_key", "")).strip(),
        "paytm_vpa": (body.paytm_vpa if body.paytm_vpa is not None else shop.get("paytm_vpa", "")).strip(),
        "paytm_enabled": int(body.paytm_enabled) if body.paytm_enabled is not None else int(shop.get("paytm_enabled", 0)),
        "phonepe_client_id": (body.phonepe_client_id if body.phonepe_client_id is not None else shop.get("phonepe_client_id", "")).strip(),
        "phonepe_client_secret": (body.phonepe_client_secret if body.phonepe_client_secret is not None else shop.get("phonepe_client_secret", "")).strip(),
        "phonepe_client_version": int(body.phonepe_client_version) if body.phonepe_client_version is not None else int(shop.get("phonepe_client_version", 1)),
        "phonepe_env": (body.phonepe_env if body.phonepe_env is not None else shop.get("phonepe_env", "PRODUCTION")).strip(),
        "phonepe_enabled": int(body.phonepe_enabled) if body.phonepe_enabled is not None else int(shop.get("phonepe_enabled", 0)),
        "smbupi_api_key": (body.smbupi_api_key if body.smbupi_api_key is not None else shop.get("smbupi_api_key", "")).strip(),
        "smbupi_api_secret": (body.smbupi_api_secret if body.smbupi_api_secret is not None else shop.get("smbupi_api_secret", "")).strip(),
        "smbupi_webhook_secret": (body.smbupi_webhook_secret if body.smbupi_webhook_secret is not None else shop.get("smbupi_webhook_secret", "")).strip(),
        "smbupi_enabled": int(body.smbupi_enabled) if body.smbupi_enabled is not None else int(shop.get("smbupi_enabled", 0))
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
        "rate_double_bw": shop.get("rate_double_bw", 3.0),
        "rate_double_color": shop.get("rate_double_color", 15.0),
        "upi_id": shop["upi_id"],
        "shop_qr_image": shop["shop_qr_image"],
        "is_active": bool(shop["is_active"]),
        "subscription_valid": is_valid,
        "paytm_enabled": bool(shop.get("paytm_enabled") and shop.get("paytm_vpa")),
        "phonepe_enabled": bool(shop.get("phonepe_enabled") and shop.get("phonepe_client_id") and shop.get("phonepe_client_secret")),
        "smbupi_enabled": bool(shop.get("smbupi_enabled") and shop.get("smbupi_api_key") and shop.get("smbupi_api_secret"))
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
    
    is_paytm_auto = bool(shop.get("paytm_enabled") and shop.get("paytm_mid") and shop.get("paytm_merchant_key") and shop.get("paytm_vpa"))
    if is_paytm_auto:
        upi_uri = generate_paytm_upi_uri(
            paytm_vpa=shop["paytm_vpa"],
            merchant_name=shop.get("shop_name", "Print"),
            amount=total,
            order_id=job["id"]
        )
    else:
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
        "print_side": "single",
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
        "upi_id": (shop.get("paytm_vpa") if is_paytm_auto else shop.get("upi_id")) or "",
        "is_paytm_auto": is_paytm_auto
    }

class CustomerConfigureRequest(BaseModel):
    copies: int = 1
    color_mode: str = "bw"
    print_side: str = "single"
    selected_pages: str = "all"
    page_range: str = None

@app.post("/api/customer/jobs/{job_id}/configure")
def customer_configure_job(job_id: str, body: CustomerConfigureRequest):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    shop = database.get_shop_by_id(job["shop_id"])
    
    color_mode = body.color_mode
    print_side = (body.print_side or "single").lower()
    if print_side not in ["single", "double"]:
        print_side = "single"
    
    total_doc_pages = job["total_pages"]
    page_choice = body.page_range or body.selected_pages or "all"
    pages_to_print = parse_page_range(page_choice, total_doc_pages)
    num_pages = len(pages_to_print)
    copies = max(1, body.copies)

    rate_single = float(shop["rate_color"]) if color_mode == "color" else float(shop["rate_bw"])
    rate_double = float(shop.get("rate_double_color" if color_mode == "color" else "rate_double_bw") or (rate_single * 1.5))

    if print_side == "double":
        double_sheets = num_pages // 2
        single_sheets = num_pages % 2
        sheet_cost = (double_sheets * rate_double) + (single_sheets * rate_single)
        total_amount = round(sheet_cost * copies, 2)
        rate_per_page = round(total_amount / (num_pages * copies), 2) if num_pages > 0 else rate_single
    else:
        total_amount = round(num_pages * copies * rate_single, 2)
        rate_per_page = rate_single
    
    is_paytm_auto = bool(shop.get("paytm_enabled") and shop.get("paytm_mid") and shop.get("paytm_merchant_key") and shop.get("paytm_vpa"))
    if is_paytm_auto:
        upi_uri = generate_paytm_upi_uri(
            paytm_vpa=shop["paytm_vpa"],
            merchant_name=shop.get("shop_name", "Print"),
            amount=total_amount,
            order_id=job_id
        )
    else:
        upi_uri = generate_upi_uri(
            upi_id=shop.get("upi_id") or "merchant@upi",
            merchant_name=shop.get("shop_name", "Print"),
            amount=total_amount,
            order_id=job_id
        )
    qr_b64 = generate_qr_base64(upi_uri)

    # PhonePe Standard Checkout session
    is_phonepe_auto = bool(shop.get("phonepe_enabled") and shop.get("phonepe_client_id") and shop.get("phonepe_client_secret"))
    phonepe_pay_url = ""
    if is_phonepe_auto:
        phonepe_res = initiate_phonepe_checkout(
            client_id=shop["phonepe_client_id"],
            client_secret=shop["phonepe_client_secret"],
            client_version=shop.get("phonepe_client_version", 1),
            env_str=shop.get("phonepe_env", "PRODUCTION"),
            amount=total_amount,
            order_id=job_id,
            redirect_url=f"/s/{shop['slug']}?job={job_id}&paid=1"
        )
        if phonepe_res.get("success"):
            phonepe_pay_url = phonepe_res.get("redirect_url", "")

    # SMB UPI (smbupi.com 0% fee gateway) order session
    is_smbupi_auto = bool(shop.get("smbupi_enabled") and shop.get("smbupi_api_key") and shop.get("smbupi_api_secret"))
    smbupi_pay_url = ""
    if is_smbupi_auto:
        base_url = get_base_url()
        callback_url = f"{base_url}/s/{shop['slug']}?job={job_id}&smbpaid=1"
        smb_res = create_smbupi_order(
            api_key=shop["smbupi_api_key"],
            api_secret=shop["smbupi_api_secret"],
            amount=total_amount,
            order_id=job_id,
            callback_url=callback_url,
            customer_name="Customer",
            description=f"Print {shop.get('shop_name', 'Order')} #{job_id[:6]}"
        )
        if smb_res.get("success"):
            smbupi_pay_url = smb_res.get("payment_url", "")
    
    updated = database.update_job_status(job_id, {
        "num_pages_to_print": num_pages,
        "copies": copies,
        "color_mode": color_mode,
        "print_side": print_side,
        "rate_per_page": rate_per_page,
        "total_amount": total_amount,
        "phonepe_order_id": job_id,
        "phonepe_redirect_url": phonepe_pay_url,
        "smbupi_payment_url": smbupi_pay_url
    })
    
    return {
        **updated,
        "job": updated,
        "upi_uri": upi_uri,
        "qr_code": qr_b64,
        "qr_code_base64": qr_b64,
        "shop_qr_image": shop.get("shop_qr_image", ""),
        "upi_id": (shop.get("paytm_vpa") if is_paytm_auto else shop.get("upi_id")) or "",
        "is_paytm_auto": is_paytm_auto,
        "is_phonepe_auto": is_phonepe_auto,
        "phonepe_pay_url": phonepe_pay_url,
        "is_smbupi_auto": is_smbupi_auto,
        "smbupi_pay_url": smbupi_pay_url
    }

@app.post("/api/customer/jobs/{job_id}/check-phonepe-status")
def customer_check_phonepe_status(job_id: str, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("payment_status") == "paid":
        return {"success": True, "status": "COMPLETED", "job": job}
    
    shop = database.get_shop_by_id(job["shop_id"])
    if not shop or not shop.get("phonepe_enabled") or not shop.get("phonepe_client_id") or not shop.get("phonepe_client_secret"):
        return {"success": False, "status": "NOT_CONFIGURED", "message": "PhonePe Standard Checkout is not enabled for this shop"}
    
    res = check_phonepe_order_status(
        client_id=shop["phonepe_client_id"],
        client_secret=shop["phonepe_client_secret"],
        client_version=shop.get("phonepe_client_version", 1),
        env_str=shop.get("phonepe_env", "PRODUCTION"),
        order_id=job_id
    )
    
    if res.get("success") and res.get("status") == "COMPLETED":
        updated = database.update_job_status(job_id, {
            "payment_status": "paid",
            "print_status": "printing",
            "phonepe_order_id": res.get("order_id", job_id)
        })
        background_tasks.add_task(trigger_print_execution, job_id)
        return {"success": True, "status": "COMPLETED", "job": updated, "order_id": res.get("order_id")}
    
    return {"success": False, "status": res.get("status", "PENDING"), "message": res.get("message", "")}

@app.post("/api/customer/jobs/{job_id}/check-paytm-status")
def customer_check_paytm_status(job_id: str, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("payment_status") == "paid":
        return {"success": True, "status": "TXN_SUCCESS", "job": job}
    
    shop = database.get_shop_by_id(job["shop_id"])
    if not shop or not shop.get("paytm_enabled") or not shop.get("paytm_mid") or not shop.get("paytm_merchant_key"):
        return {"success": False, "status": "NOT_CONFIGURED", "message": "Paytm Business is not enabled for this shop"}
    
    res = check_paytm_order_status(
        mid=shop["paytm_mid"],
        merchant_key=shop["paytm_merchant_key"],
        order_id=job_id
    )
    
    if res.get("success") and res.get("status") == "TXN_SUCCESS":
        updated = database.update_job_status(job_id, {
            "payment_status": "paid",
            "print_status": "printing",
            "paytm_txn_id": res.get("txn_id", "")
        })
        background_tasks.add_task(trigger_print_execution, job_id)
        return {"success": True, "status": "TXN_SUCCESS", "job": updated, "txn_id": res.get("txn_id")}
    
    return {"success": False, "status": res.get("status", "PENDING"), "message": res.get("message", "")}

@app.post("/api/customer/jobs/{job_id}/check-smbupi-status")
def customer_check_smbupi_status(job_id: str, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("payment_status") == "paid":
        return {"success": True, "status": "success", "job": job}
    
    shop = database.get_shop_by_id(job["shop_id"])
    if not shop or not shop.get("smbupi_enabled") or not shop.get("smbupi_api_key") or not shop.get("smbupi_api_secret"):
        return {"success": False, "status": "not_configured", "message": "SMB UPI Gateway is not enabled for this shop"}
    
    res = check_smbupi_order_status(
        api_key=shop["smbupi_api_key"],
        api_secret=shop["smbupi_api_secret"],
        order_id=job_id
    )
    
    if res.get("success") and res.get("status") == "success":
        updated = database.update_job_status(job_id, {
            "payment_status": "paid",
            "print_status": "printing"
        })
        background_tasks.add_task(trigger_print_execution, job_id)
        return {"success": True, "status": "success", "job": updated, "utr": res.get("utr", "")}
    
    return {"success": False, "status": res.get("status", "pending"), "message": res.get("error", "")}

# ==================== PAYMENT WEBHOOKS (PHONEPE, PAYTM & SMBUPI) ====================

@app.post("/api/webhooks/phonepe")
async def phonepe_webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Receives instant payment notifications from PhonePe.
    Triggers automated print execution immediately when payment is confirmed.
    """
    try:
        body_bytes = await request.body()
        if not body_bytes:
            return {"status": "SUCCESS", "message": "Empty body acknowledged"}
        
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            payload = {}
        
        # If response is Base64 encoded (Standard PhonePe pattern)
        if "response" in payload and isinstance(payload["response"], str):
            try:
                decoded = base64.b64decode(payload["response"]).decode("utf-8")
                payload = json.loads(decoded)
            except Exception:
                pass
        
        order_id = ""
        state = ""
        
        if "payload" in payload and isinstance(payload["payload"], dict):
            p = payload["payload"]
            order_id = p.get("merchantOrderId") or p.get("orderId") or ""
            state = (p.get("state") or "").upper()
        elif "data" in payload and isinstance(payload["data"], dict):
            d = payload["data"]
            order_id = d.get("merchantTransactionId") or d.get("merchantOrderId") or d.get("orderId") or ""
            state = (d.get("state") or d.get("responseCode") or payload.get("code") or "").upper()
        else:
            order_id = payload.get("merchantOrderId") or payload.get("merchantTransactionId") or payload.get("orderId") or ""
            state = (payload.get("state") or payload.get("code") or "").upper()
        
        is_success = state in ["COMPLETED", "SUCCESS", "PAYMENT_SUCCESS"]
        
        if order_id:
            job = database.get_job(order_id)
            if job and is_success and job.get("payment_status") != "paid":
                database.update_job_status(order_id, {
                    "payment_status": "paid",
                    "print_status": "printing"
                })
                background_tasks.add_task(trigger_print_execution, order_id)
                print(f"[PHONEPE WEBHOOK] Successfully verified order {order_id}. Printing triggered!")
        
        return {"status": "SUCCESS", "message": "Webhook processed successfully"}
    except Exception as e:
        print(f"[PHONEPE WEBHOOK ERROR] {e}")
        return {"status": "SUCCESS", "message": str(e)}

@app.post("/api/webhooks/paytm")
async def paytm_webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Receives instant payment notifications from Paytm Business.
    Triggers automated print execution immediately when payment is confirmed.
    """
    try:
        content_type = request.headers.get("content-type", "")
        data = {}
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)
        
        order_id = data.get("ORDERID") or data.get("orderId") or ""
        status = (data.get("STATUS") or data.get("status") or "").upper()
        
        if order_id and status in ["TXN_SUCCESS", "SUCCESS"]:
            job = database.get_job(order_id)
            if job and job.get("payment_status") != "paid":
                database.update_job_status(order_id, {
                    "payment_status": "paid",
                    "print_status": "printing",
                    "paytm_txn_id": data.get("TXNID", "")
                })
                background_tasks.add_task(trigger_print_execution, order_id)
                print(f"[PAYTM WEBHOOK] Successfully verified order {order_id}. Printing triggered!")
        
        return {"status": "SUCCESS", "message": "Paytm webhook processed"}
    except Exception as e:
        print(f"[PAYTM WEBHOOK ERROR] {e}")
        return {"status": "SUCCESS", "message": str(e)}

@app.post("/api/webhooks/smbupi")
async def smbupi_webhook_handler(request: Request, background_tasks: BackgroundTasks):
    """
    Receives instant payment notifications from SMB UPI (smbupi.com).
    Triggers automated print execution immediately when payment is confirmed.
    """
    try:
        body_bytes = await request.body()
        if not body_bytes:
            return {"status": "SUCCESS", "message": "Empty body acknowledged"}
        
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            payload = {}
        
        order_id = payload.get("order_id") or payload.get("orderId") or ""
        if not order_id and "data" in payload and isinstance(payload["data"], dict):
            order_id = payload["data"].get("order_id") or payload["data"].get("orderId") or ""
        
        status = (payload.get("status") or payload.get("payment_status") or "").lower()
        if not status and "data" in payload and isinstance(payload["data"], dict):
            status = (payload["data"].get("payment_status") or payload["data"].get("status") or "").lower()
        
        event = (payload.get("event") or "").lower()
        is_success = (status == "success" or event in ["payment.success", "order.paid", "success"])
        
        if order_id and is_success:
            job = database.get_job(order_id)
            if job and job.get("payment_status") != "paid":
                database.update_job_status(order_id, {
                    "payment_status": "paid",
                    "print_status": "printing"
                })
                background_tasks.add_task(trigger_print_execution, order_id)
                print(f"[SMBUPI WEBHOOK] Successfully verified order {order_id}. Printing triggered!")
        
        return {"status": "SUCCESS", "message": "SMB UPI webhook processed"}
    except Exception as e:
        print(f"[SMBUPI WEBHOOK ERROR] {e}")
        return {"status": "SUCCESS", "message": str(e)}

@app.get("/api/customer/jobs/{job_id}/status")
def customer_get_status(job_id: str):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/customer/jobs/{job_id}/pay-claimed")
def customer_claim_paid(job_id: str, background_tasks: BackgroundTasks):
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    shop = database.get_shop_by_id(job["shop_id"])
    auto_print = bool(shop.get("auto_print_enabled", 1)) if shop else True
    
    if auto_print:
        # ⚡ Instant Auto-Print Mode: directly trigger print without waiting!
        updated = database.update_job_status(job_id, {
            "payment_status": "paid",
            "print_status": "printing"
        })
        background_tasks.add_task(trigger_print_execution, job_id)
        return {"success": True, "job": updated, "auto_printed": True}
    else:
        # Manual Merchant Approval Mode: waits for shopkeeper to click approve
        updated = database.update_job_status(job_id, {
            "payment_status": "claimed",
            "print_status": "waiting_merchant"
        })
        return {"success": True, "job": updated, "auto_printed": False}

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
    c.execute("""
        SELECT * FROM jobs 
        WHERE shop_id = ? 
          AND (
            (payment_status = 'paid' AND print_status = 'printing')
            OR (print_status = 'printing')
            OR (payment_status IN ('paid', 'confirmed') AND print_status IN ('printing', 'approved'))
          )
        ORDER BY created_at ASC
    """, (shop_id,))
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

CONNECTOR_HEARTBEATS = {}

class ConnectorHeartbeatRequest(BaseModel):
    shop_id: str
    token: str
    status: str = "online"
    active_printer: Optional[str] = ""
    printers: Optional[list] = []

@app.post("/api/connector/heartbeat")
def connector_heartbeat(body: ConnectorHeartbeatRequest):
    shop = database.get_shop_by_id(body.shop_id)
    if not shop or shop["connector_token"] != body.token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    CONNECTOR_HEARTBEATS[body.shop_id] = {
        "last_seen": time.time(),
        "status": body.status,
        "active_printer": body.active_printer,
        "printers": body.printers
    }
    return {"success": True}

@app.get("/api/shop/{shop_id}/connector-status")
def get_connector_status(shop_id: str):
    hb = CONNECTOR_HEARTBEATS.get(shop_id)
    now = time.time()
    if hb and (now - hb["last_seen"]) < 20:
        return {
            "online": True,
            "active_printer": hb.get("active_printer", ""),
            "printers": hb.get("printers", []),
            "last_seen_seconds_ago": int(now - hb["last_seen"])
        }
    return {
        "online": False,
        "active_printer": "",
        "printers": [],
        "last_seen_seconds_ago": int(now - hb["last_seen"]) if hb else None
    }

@app.get("/api/connector/download-app")
def download_windows_app():
    exe_path = BASE_DIR / "dist" / "SmartPrintConnect.exe"
    if not exe_path.exists():
        exe_path = BASE_DIR / "SmartPrintConnect.exe"
    if exe_path.exists():
        return FileResponse(exe_path, media_type="application/octet-stream", filename="SmartPrintConnect.exe")
    
    zip_path = Path("C:/Users/Jagannath/Downloads/smartprint_fixed_files.zip")
    if zip_path.exists():
        return FileResponse(zip_path, media_type="application/zip", filename="SmartPrintApp_Windows.zip")
    return FileResponse(BASE_DIR / "smart_print_app.py", media_type="text/plain", filename="smart_print_app.py")

@app.get("/api/connector/config/{shop_id}")
def download_connector_config(shop_id: str):
    shop = database.get_shop_by_id(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    base_url = get_base_url()
    cfg = {
        "server_url": base_url,
        "shop_id": shop["shop_id"],
        "token": shop["connector_token"],
        "printer": shop.get("selected_printer") or "",
        "bw_printer": "",
        "color_printer": "",
        "multi_printer_enabled": False,
        "auto_duplex": True,
        "auto_start": False
    }
    return Response(
        content=json.dumps(cfg, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="connector_config.json"'}
    )

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

if not exist change_printer.bat (
    (
        echo @echo off
        echo title Smart Print - Change Printer Setup
        echo color 0b
        echo python print_connector.py --configure
        echo pause
    ) > change_printer.bat
)

echo Starting Smart Print Connector...
python print_connector.py
pause
"""
    return PlainTextResponse(bat_content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=start_connector_{shop['slug']}.bat"})

@app.get("/api/connector/download-change-printer/{shop_id}")
def download_change_printer_launcher(shop_id: str):
    shop = database.get_shop_by_id(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    bat_content = f"""@echo off
title Smart Print - Change Printer Setup ({shop['shop_name']})
color 0b
echo ========================================================
echo    SMART PRINT - PRINTER SELECTION & MULTI-PRINTER SETUP
echo    Shop: {shop['shop_name']}
echo ========================================================
python print_connector.py --configure
pause
"""
    return PlainTextResponse(bat_content, media_type="text/plain", headers={"Content-Disposition": f"attachment; filename=change_printer_{shop['slug']}.bat"})

@app.get("/api/printers")
def list_printers():
    return {"printers": get_installed_printers()}

class TestPrintRequest(BaseModel):
    printer_name: str = ""
    shop_id: Optional[str] = ""

@app.post("/api/test-print")
def run_test_print(body: TestPrintRequest):
    try:
        shop = database.get_shop_by_id(body.shop_id) if body.shop_id else None
        shop_name = shop["shop_name"] if shop else "Smart Print"
        target_printer = body.printer_name or (shop.get("selected_printer") if shop else "")
        job_id = "JOB-TEST-" + uuid.uuid4().hex[:6].upper()
        test_pdf = UPLOADS_DIR / f"{job_id}.pdf"
        generate_test_page_pdf(printer_name=target_printer or "System Default", shop_name=shop_name, output_path=str(test_pdf))
        
        # If running on Cloud (Render / Linux / no local Windows printer attached to server),
        # queue an approved test print job so Windows Desktop Agent prints it automatically!
        is_windows = (os.name == "nt")
        if (not is_windows or not SUMATRA_PATH.exists()) and body.shop_id:
            database.create_job({
                "id": job_id,
                "shop_id": body.shop_id,
                "original_name": "Test_Print_Page.pdf",
                "pdf_path": str(test_pdf),
                "total_pages": 1,
                "num_pages_to_print": 1,
                "copies": 1,
                "color_mode": "bw",
                "print_side": "single",
                "rate_per_page": 0.0,
                "total_amount": 0.0,
                "payment_status": "paid",
                "print_status": "printing",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            return {"success": True, "method": "cloud_connector", "message": "Test print queued for Windows Desktop Agent"}
        
        res = print_pdf(str(test_pdf), printer_name=body.printer_name or None, copies=1, color_mode="bw")
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

class SuperAdminShopUpdateRequest(BaseModel):
    pin: str
    shop_id: str
    shop_name: str
    owner_name: str
    mobile: str
    slug: str
    password: Optional[str] = None
    upi_id: Optional[str] = ""
    rate_bw: float = 2.0
    rate_double_bw: Optional[float] = 3.0
    rate_color: float = 10.0
    rate_double_color: Optional[float] = 15.0
    is_active: int = 1
    subscription_expires_at: Optional[str] = None

@app.post("/api/superadmin/shop/update")
def superadmin_update_shop_endpoint(body: SuperAdminShopUpdateRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    data = body.model_dump()
    res = database.superadmin_update_shop(body.shop_id, data)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return {"success": True}

class SuperAdminResetPasswordRequest(BaseModel):
    pin: str
    shop_id: str
    new_password: str

@app.post("/api/superadmin/shop/reset-password")
def superadmin_reset_password_endpoint(body: SuperAdminResetPasswordRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    if not body.new_password or len(body.new_password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
        
    database.superadmin_reset_password(body.shop_id, body.new_password.strip())
    return {"success": True}

class SuperAdminDeleteShopRequest(BaseModel):
    pin: str
    shop_id: str

@app.post("/api/superadmin/shop/delete")
def superadmin_delete_shop_endpoint(body: SuperAdminDeleteShopRequest):
    master_pin = database.get_saas_setting("master_pin", "1234")
    if body.pin.strip() != master_pin:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    database.superadmin_delete_shop(body.shop_id)
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
