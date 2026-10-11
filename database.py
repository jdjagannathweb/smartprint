import sqlite3
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path

DB_FILE = Path(__file__).parent / "database.db"

def get_connection():
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Shops table (Members)
    c.execute("""
    CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id TEXT UNIQUE NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        shop_name TEXT NOT NULL,
        owner_name TEXT NOT NULL,
        mobile TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        upi_id TEXT DEFAULT '',
        upi_name TEXT DEFAULT '',
        shop_qr_image TEXT DEFAULT '',
        rate_bw REAL DEFAULT 2.0,
        rate_color REAL DEFAULT 10.0,
        rate_double_bw REAL DEFAULT 3.0,
        rate_double_color REAL DEFAULT 15.0,
        selected_printer TEXT DEFAULT '',
        auto_print_enabled INTEGER DEFAULT 1,
        connector_token TEXT NOT NULL,
        subscription_plan TEXT DEFAULT 'plan1_free',
        subscription_expires_at TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """)
    
    # Safe migration for existing databases
    try:
        c.execute("ALTER TABLE shops ADD COLUMN rate_double_bw REAL DEFAULT 3.0")
        conn.commit()
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE shops ADD COLUMN rate_double_color REAL DEFAULT 15.0")
        conn.commit()
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE shops ADD COLUMN auto_print_enabled INTEGER DEFAULT 1")
        conn.commit()
    except Exception:
        pass
    
    # 2. Print Jobs table
    c.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        shop_id TEXT NOT NULL,
        original_name TEXT NOT NULL,
        pdf_path TEXT NOT NULL,
        total_pages INTEGER DEFAULT 1,
        num_pages_to_print INTEGER DEFAULT 1,
        copies INTEGER DEFAULT 1,
        color_mode TEXT DEFAULT 'bw',
        print_side TEXT DEFAULT 'single',
        rate_per_page REAL DEFAULT 2.0,
        total_amount REAL DEFAULT 2.0,
        payment_status TEXT DEFAULT 'pending',
        print_status TEXT DEFAULT 'queued',
        print_error TEXT,
        created_at TEXT NOT NULL
    )
    """)
    
    # Safe migration for existing databases
    try:
        c.execute("ALTER TABLE jobs ADD COLUMN print_side TEXT DEFAULT 'single'")
        conn.commit()
    except Exception:
        pass
    
    # 3. SaaS / Platform Settings
    c.execute("""
    CREATE TABLE IF NOT EXISTS saas_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)
    
    # 4. Renewal / Subscription Requests
    c.execute("""
    CREATE TABLE IF NOT EXISTS renewal_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id TEXT NOT NULL,
        plan_code TEXT NOT NULL,
        plan_name TEXT NOT NULL,
        amount REAL NOT NULL,
        duration_days INTEGER NOT NULL,
        payment_ref TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL
    )
    """)
    
    # Default SaaS Settings if not exists
    defaults = {
        "master_pin": "1234",
        "plan1_name": "୬ ମାସ ପ୍ଲାନ୍ (6 Months Plan)",
        "plan1_days": "180",
        "plan1_price": "499",
        "plan2_name": "୧ ବର୍ଷ ପ୍ଲାନ୍ (1 Year Plan - Best Value)",
        "plan2_days": "365",
        "plan2_price": "899",
        "superadmin_upi_id": "9937037131@ybl",
        "superadmin_upi_name": "Smart Print Super Admin",
        "free_trial_days": "180"
    }
    
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO saas_settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

# ---------- SHOP FUNCTIONS ----------

def register_shop(shop_name, owner_name, mobile, password, slug=None, upi_id=""):
    conn = get_connection()
    c = conn.cursor()
    
    # Clean mobile number: strip country code and non-digits
    clean_mob = "".join(ch for ch in str(mobile) if ch.isdigit())
    if len(clean_mob) > 10 and clean_mob.startswith("91"):
        clean_mob = clean_mob[2:]
    
    if len(clean_mob) != 10:
        conn.close()
        return {"error": "ଦୟାକରି ସଠିକ୍ ୧୦-ଅଙ୍କ ମୋବାଇଲ୍ ନମ୍ବର ଦିଅନ୍ତୁ (10-digit mobile number required)."}
    
    mobile = clean_mob

    # Check if mobile already exists
    c.execute("SELECT id, shop_name FROM shops WHERE mobile = ?", (mobile,))
    existing = c.fetchone()
    if existing:
        conn.close()
        return {"error": f"ଏହି ମୋବାଇଲ୍ ନମ୍ବର ({mobile}) ପୂର୍ବରୁ ପଞ୍ଜିକୃତ ହୋଇସାରିଛି। ଦୟାକରି ଲଗ୍ଇନ୍ କରନ୍ତୁ।"}

    # Clean slug (strictly ASCII for clean URLs)
    def to_ascii_slug(text):
        return "".join(ch for ch in text.lower() if ('a' <= ch <= 'z') or ('0' <= ch <= '9') or ch in "-_ ")

    if not slug or not slug.strip():
        clean_name = to_ascii_slug(shop_name).strip().replace(" ", "-")
        slug = clean_name if clean_name else f"shop-{mobile[-4:]}"
    slug = "".join(ch for ch in slug.lower() if ('a' <= ch <= 'z') or ('0' <= ch <= '9') or ch in "-_")
    if not slug:
        slug = f"shop-{mobile[-4:]}"
        
    # Ensure unique slug
    base_slug = slug
    while True:
        c.execute("SELECT id FROM shops WHERE slug = ?", (slug,))
        if not c.fetchone():
            break
        slug = f"{base_slug}-{uuid.uuid4().hex[:4]}"
        
    shop_id = "SHP-" + uuid.uuid4().hex[:6].upper()
    connector_token = "TOK-" + uuid.uuid4().hex[:12].upper()
    now = datetime.now()
    
    # 6 MONTHS FREE TRIAL (180 DAYS)
    trial_days = int(get_saas_setting("free_trial_days", 180))
    expires_at = now + timedelta(days=trial_days)
    
    try:
        c.execute("""
        INSERT INTO shops (
            shop_id, slug, shop_name, owner_name, mobile, password,
            upi_id, upi_name, rate_bw, rate_color, rate_double_bw, rate_double_color, connector_token,
            subscription_plan, subscription_expires_at, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2.0, 10.0, 3.0, 15.0, ?, 'plan1_free', ?, 1, ?)
        """, (
            shop_id, slug, shop_name, owner_name, mobile, password,
            upi_id, owner_name, connector_token,
            expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        return get_shop_by_id(shop_id)
    except sqlite3.IntegrityError:
        return {"error": "ଏହି ମୋବାଇଲ୍ ନମ୍ବର କିମ୍ବା ୟୁଜରନେମ୍ ପୂର୍ବରୁ ପଞ୍ଜିକୃତ ହୋଇସାରିଛି।"}
    finally:
        conn.close()

def get_shop_by_id(shop_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM shops WHERE shop_id = ?", (shop_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_shop_by_slug(slug):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM shops WHERE slug = ?", (slug.lower(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_shop_by_mobile(mobile):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM shops WHERE mobile = ?", (mobile,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_shop_settings(shop_id, updates):
    conn = get_connection()
    c = conn.cursor()
    fields = []
    values = []
    allowed = ["shop_name", "owner_name", "upi_id", "upi_name", "shop_qr_image",
               "rate_bw", "rate_color", "rate_double_bw", "rate_double_color",
               "selected_printer", "auto_print_enabled", "password", "is_active"]
    for k in allowed:
        if k in updates:
            fields.append(f"{k} = ?")
            values.append(updates[k])
    if fields:
        values.append(shop_id)
        c.execute(f"UPDATE shops SET {', '.join(fields)} WHERE shop_id = ?", values)
        conn.commit()
    conn.close()
    return get_shop_by_id(shop_id)

def is_subscription_valid(shop):
    if not shop:
        return False
    if not shop.get("is_active"):
        return False
    exp_str = shop.get("subscription_expires_at")
    if not exp_str:
        return False
    try:
        exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        return exp_dt > datetime.now()
    except Exception:
        return False

def get_subscription_days_left(shop):
    exp_str = shop.get("subscription_expires_at")
    if not exp_str:
        return 0
    try:
        exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        diff = (exp_dt - datetime.now()).days
        return max(0, diff)
    except Exception:
        return 0

# ---------- JOBS FUNCTIONS ----------

def create_job(job_data):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO jobs (
        id, shop_id, original_name, pdf_path, total_pages, num_pages_to_print,
        copies, color_mode, print_side, rate_per_page, total_amount, payment_status,
        print_status, print_error, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_data["id"], job_data["shop_id"], job_data["original_name"], job_data["pdf_path"],
        job_data.get("total_pages", 1), job_data.get("num_pages_to_print", 1),
        job_data.get("copies", 1), job_data.get("color_mode", "bw"),
        job_data.get("print_side", "single"),
        job_data.get("rate_per_page", 2.0), job_data.get("total_amount", 2.0),
        job_data.get("payment_status", "pending"), job_data.get("print_status", "queued"),
        job_data.get("print_error"), job_data.get("created_at")
    ))
    conn.commit()
    conn.close()
    return get_job(job_data["id"])

def get_job(job_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_job_status(job_id, updates):
    conn = get_connection()
    c = conn.cursor()
    fields = []
    values = []
    for k in ["num_pages_to_print", "copies", "color_mode", "print_side", "rate_per_page", "total_amount", "payment_status", "print_status", "print_error"]:
        if k in updates:
            fields.append(f"{k} = ?")
            values.append(updates[k])
    if fields:
        values.append(job_id)
        c.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    conn.close()
    return get_job(job_id)

def get_shop_jobs(shop_id, limit=50):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM jobs WHERE shop_id = ? ORDER BY rowid DESC, created_at DESC LIMIT ?", (shop_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_shop_stats(shop_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total_jobs, SUM(CASE WHEN payment_status='paid' THEN total_amount ELSE 0 END) as revenue, SUM(CASE WHEN print_status='printed' THEN 1 ELSE 0 END) as printed, SUM(CASE WHEN payment_status='claimed' THEN 1 ELSE 0 END) as claimed FROM jobs WHERE shop_id = ?", (shop_id,))
    row = dict(c.fetchone())
    conn.close()
    return {
        "total_jobs": row["total_jobs"] or 0,
        "total_revenue": round(row["revenue"] or 0, 2),
        "total_printed": row["printed"] or 0,
        "total_claimed": row["claimed"] or 0
    }

def delete_job(job_id, shop_id=None):
    conn = get_connection()
    c = conn.cursor()
    if shop_id:
        c.execute("DELETE FROM jobs WHERE id = ? AND shop_id = ?", (job_id, shop_id))
    else:
        c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return True

# ---------- SAAS SUPERADMIN FUNCTIONS ----------

def get_saas_setting(key, default=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM saas_settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else str(default)

def set_saas_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO saas_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_all_saas_settings():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM saas_settings")
    rows = {r["key"]: r["value"] for r in c.fetchall()}
    conn.close()
    return rows

def get_all_shops_for_superadmin():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT s.*,
           COUNT(j.id) as job_count,
           COALESCE(SUM(j.total_pages * j.copies), 0) as total_pages_printed
    FROM shops s
    LEFT JOIN jobs j ON s.shop_id = j.shop_id AND j.print_status = 'printed'
    GROUP BY s.id
    ORDER BY s.id DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    
    # Calculate days left and status for each shop
    for s in rows:
        s["days_left"] = get_subscription_days_left(s)
        s["is_valid"] = is_subscription_valid(s)
    return rows

def get_superadmin_overview():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total_shops FROM shops")
    total_shops = c.fetchone()["total_shops"] or 0
    
    c.execute("SELECT COUNT(*) as total_jobs, COALESCE(SUM(total_pages * copies), 0) as total_pages FROM jobs WHERE print_status = 'printed'")
    job_row = c.fetchone()
    total_jobs = job_row["total_jobs"] or 0
    total_pages = job_row["total_pages"] or 0
    
    shops = get_all_shops_for_superadmin()
    active_shops = sum(1 for s in shops if s["is_valid"])
    expired_shops = total_shops - active_shops
    
    conn.close()
    return {
        "total_shops": total_shops,
        "active_shops": active_shops,
        "expired_shops": expired_shops,
        "total_jobs": total_jobs,
        "total_pages": total_pages
    }

def extend_shop_subscription(shop_id, days):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT subscription_expires_at FROM shops WHERE shop_id = ?", (shop_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
        
    cur_exp = row["subscription_expires_at"]
    try:
        cur_dt = datetime.strptime(cur_exp, "%Y-%m-%d %H:%M:%S")
        start_from = max(cur_dt, datetime.now())
    except Exception:
        start_from = datetime.now()
        
    new_dt = start_from + timedelta(days=days)
    c.execute("UPDATE shops SET subscription_expires_at = ?, is_active = 1 WHERE shop_id = ?", (new_dt.strftime("%Y-%m-%d %H:%M:%S"), shop_id))
    conn.commit()
    conn.close()
    return new_dt.strftime("%Y-%m-%d %H:%M:%S")

def toggle_shop_active(shop_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT is_active FROM shops WHERE shop_id = ?", (shop_id,))
    row = c.fetchone()
    if row:
        new_status = 0 if row["is_active"] else 1
        c.execute("UPDATE shops SET is_active = ? WHERE shop_id = ?", (new_status, shop_id))
        conn.commit()
    conn.close()
    return True

def superadmin_update_shop(shop_id, data):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, mobile, slug FROM shops WHERE shop_id = ?", (shop_id,))
    shop = c.fetchone()
    if not shop:
        conn.close()
        return {"error": "ଦୋକାନୀ ମିଳିଲା ନାହିଁ (Shop not found)"}
    
    # Check mobile uniqueness if changed
    new_mobile = str(data.get("mobile", "")).strip()
    if new_mobile and new_mobile != shop["mobile"]:
        c.execute("SELECT id FROM shops WHERE mobile = ? AND shop_id != ?", (new_mobile, shop_id))
        if c.fetchone():
            conn.close()
            return {"error": f"ଏହି ମୋବାଇଲ୍ ନମ୍ବର ({new_mobile}) ଅନ୍ୟ ଏକ ଦୋକାନରେ ପୂର୍ବରୁ ପଞ୍ଜିକୃତ ଅଛି!"}
            
    # Check slug uniqueness if changed
    new_slug = str(data.get("slug", "")).strip().lower()
    if new_slug and new_slug != shop["slug"]:
        c.execute("SELECT id FROM shops WHERE slug = ? AND shop_id != ?", (new_slug, shop_id))
        if c.fetchone():
            conn.close()
            return {"error": f"ଏହି ୱେବ୍ Slug ({new_slug}) ଅନ୍ୟ ଏକ ଦୋକାନରେ ପୂର୍ବରୁ ବ୍ୟବହୃତ ହୋଇଛି!"}

    fields = []
    params = []
    
    if "shop_name" in data and data["shop_name"]:
        fields.append("shop_name = ?")
        params.append(str(data["shop_name"]).strip())
    if "owner_name" in data and data["owner_name"]:
        fields.append("owner_name = ?")
        params.append(str(data["owner_name"]).strip())
    if new_mobile:
        fields.append("mobile = ?")
        params.append(new_mobile)
    if new_slug:
        fields.append("slug = ?")
        params.append(new_slug)
    if "password" in data and data["password"]:
        fields.append("password = ?")
        params.append(str(data["password"]).strip())
    if "upi_id" in data:
        fields.append("upi_id = ?")
        params.append(str(data["upi_id"] or "").strip())
    if "rate_bw" in data and data["rate_bw"] is not None:
        fields.append("rate_bw = ?")
        params.append(float(data["rate_bw"]))
    if "rate_double_bw" in data and data["rate_double_bw"] is not None:
        fields.append("rate_double_bw = ?")
        params.append(float(data["rate_double_bw"]))
    if "rate_color" in data and data["rate_color"] is not None:
        fields.append("rate_color = ?")
        params.append(float(data["rate_color"]))
    if "rate_double_color" in data and data["rate_double_color"] is not None:
        fields.append("rate_double_color = ?")
        params.append(float(data["rate_double_color"]))
    if "is_active" in data and data["is_active"] is not None:
        fields.append("is_active = ?")
        params.append(int(data["is_active"]))
    if "subscription_expires_at" in data and data["subscription_expires_at"]:
        fields.append("subscription_expires_at = ?")
        params.append(str(data["subscription_expires_at"]).strip())
        
    if fields:
        params.append(shop_id)
        query = f"UPDATE shops SET {', '.join(fields)} WHERE shop_id = ?"
        c.execute(query, tuple(params))
        conn.commit()
        
    conn.close()
    return {"success": True}

def superadmin_reset_password(shop_id, new_password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE shops SET password = ? WHERE shop_id = ?", (new_password.strip(), shop_id))
    conn.commit()
    conn.close()
    return True

def superadmin_delete_shop(shop_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM jobs WHERE shop_id = ?", (shop_id,))
    c.execute("DELETE FROM renewal_requests WHERE shop_id = ?", (shop_id,))
    c.execute("DELETE FROM shops WHERE shop_id = ?", (shop_id,))
    conn.commit()
    conn.close()
    return True

# Initialize DB on import
init_db()
