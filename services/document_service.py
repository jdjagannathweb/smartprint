import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from PIL import Image
from pypdf import PdfReader, PdfWriter

JOBS_FILE = Path(__file__).parent.parent / "config" / "jobs.json"
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

def load_jobs():
    if not JOBS_FILE.exists():
        return []
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_jobs(jobs):
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)

def get_job(job_id: str):
    jobs = load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            return j
    return None

def update_job(job_id: str, updates: dict):
    jobs = load_jobs()
    for j in jobs:
        if j["id"] == job_id:
            j.update(updates)
            save_jobs(jobs)
            return j
    return None

def process_uploaded_files(files_data: list[tuple[str, bytes]]) -> dict:
    """
    Accepts a list of (original_name, file_bytes).
    Converts images to PDF, merges all PDFs/images into a single combined PDF,
    and returns the consolidated job_data dictionary.
    """
    if not files_data:
        raise ValueError("No files provided")
        
    job_id = "PJ-" + uuid.uuid4().hex[:8].upper()
    target_pdf = UPLOADS_DIR / f"{job_id}.pdf"
    
    writer = PdfWriter()
    files_info = []
    total_pages = 0
    
    import io
    for filename, file_bytes in files_data:
        if not file_bytes:
            continue
        ext = Path(filename).suffix.lower()
        is_pdf = ext == ".pdf" or file_bytes.startswith(b"%PDF") or ".pdf" in filename.lower()
        is_image = ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp"] or file_bytes[:4] in [b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1', b'\x89PNG', b'RIFF']

        if is_image and not is_pdf:
            try:
                with Image.open(io.BytesIO(file_bytes)) as img:
                    rgb_img = img.convert("RGB")
                    img_pdf_io = io.BytesIO()
                    rgb_img.save(img_pdf_io, "PDF", resolution=100.0)
                    img_pdf_io.seek(0)
                    reader = PdfReader(img_pdf_io)
                    p_count = len(reader.pages)
                    for p in reader.pages:
                        writer.add_page(p)
                    total_pages += p_count
                    files_info.append({"name": filename, "pages": p_count, "type": "image"})
            except Exception as e:
                raise ValueError(f"Could not process image '{filename}': {e}")
        elif is_pdf:
            try:
                reader = PdfReader(io.BytesIO(file_bytes))
                p_count = len(reader.pages)
                for p in reader.pages:
                    writer.add_page(p)
                total_pages += p_count
                files_info.append({"name": filename, "pages": p_count, "type": "pdf"})
            except Exception as e:
                raise ValueError(f"Could not read PDF '{filename}': {e}")
        else:
            raise ValueError(f"Unsupported file format: {ext} for '{filename}'. Please upload PDF or Image.")
            
    if total_pages == 0:
        raise ValueError("Uploaded files contain 0 valid pages.")
        
    with open(target_pdf, "wb") as f:
        writer.write(f)
        
    if len(files_info) == 1:
        display_name = files_info[0]["name"]
    else:
        display_name = f"{files_info[0]['name']} + {len(files_info)-1} more ({len(files_info)} files)"
        
    job_data = {
        "id": job_id,
        "original_name": display_name,
        "pdf_path": str(target_pdf),
        "total_pages": total_pages,
        "selected_pages": "all",
        "num_pages_to_print": total_pages,
        "copies": 1,
        "color_mode": "bw",
        "print_side": "single",
        "rate_per_page": 2.0,
        "total_amount": 2.0 * total_pages,
        "payment_status": "pending",
        "print_status": "queued",
        "print_error": None,
        "files_count": len(files_info),
        "files_info": files_info,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    jobs = load_jobs()
    jobs.insert(0, job_data)
    save_jobs(jobs)
    
    return job_data

def process_uploaded_file(original_name: str, file_bytes: bytes) -> dict:
    """Backward compatible wrapper for single file upload."""
    return process_uploaded_files([(original_name, file_bytes)])

def parse_page_range(range_str: str, max_pages: int) -> list[int]:
    """Parses range strings like '1, 3-5' into 1-based page numbers."""
    range_str = range_str.strip().lower()
    if not range_str or range_str == "all":
        return list(range(1, max_pages + 1))
    
    selected = set()
    parts = range_str.split(",")
    for part in parts:
        part = part.strip()
        if "-" in part:
            sub = part.split("-")
            if len(sub) == 2 and sub[0].strip().isdigit() and sub[1].strip().isdigit():
                start = max(1, int(sub[0].strip()))
                end = min(max_pages, int(sub[1].strip()))
                for p in range(start, end + 1):
                    selected.add(p)
        elif part.isdigit():
            val = int(part)
            if 1 <= val <= max_pages:
                selected.add(val)
    return sorted(list(selected))

def prepare_final_print_pdf(job_id: str) -> str:
    """
    If specific pages were selected, generates a trimmed PDF for printing.
    Otherwise returns original pdf path. Supports jobs from SQLite database and fallback cache.
    """
    import database
    job = database.get_job(job_id)
    if not job:
        job = get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found in database or cache")
    
    pdf_raw = job.get("pdf_path") or ""
    original_pdf = Path(pdf_raw)
    if not original_pdf.is_absolute():
        original_pdf = (Path(__file__).parent.parent / original_pdf).resolve()
    
    if not original_pdf.exists():
        fallback_uploads = UPLOADS_DIR / original_pdf.name
        if fallback_uploads.exists():
            original_pdf = fallback_uploads
        elif job_id.startswith("JOB-TEST-"):
            try:
                from services.printer_service import generate_test_page_pdf
                shop = database.get_shop_by_id(job.get("shop_id"))
                shop_name = shop.get("shop_name", "Smart Print") if shop else "Smart Print"
                token = shop.get("connector_token", "") if shop else ""
                mobile = shop.get("mobile", "") if shop else ""
                target_printer = shop.get("selected_printer", "Default Printer") if shop else "Default Printer"
                generate_test_page_pdf(
                    printer_name=target_printer,
                    shop_name=shop_name,
                    output_path=str(original_pdf),
                    shop_id=job.get("shop_id", ""),
                    connector_token=token,
                    mobile=mobile
                )
            except Exception as e:
                raise FileNotFoundError(f"Test print regeneration failed: {e}")
        else:
            raise FileNotFoundError(f"PDF file not found: {original_pdf}")
    
    selected_pages_str = job.get("selected_pages", "all")
    if not selected_pages_str or selected_pages_str == "all":
        return str(original_pdf)
    
    reader = PdfReader(str(original_pdf))
    total_pages = len(reader.pages)
    pages_to_keep = parse_page_range(selected_pages_str, total_pages)
    
    if len(pages_to_keep) == total_pages:
        return str(original_pdf)
    
    trimmed_pdf = UPLOADS_DIR / f"{job_id}_trimmed.pdf"
    writer = PdfWriter()
    for p_num in pages_to_keep:
        writer.add_page(reader.pages[p_num - 1])
    
    with open(trimmed_pdf, "wb") as f:
        writer.write(f)
    
    return str(trimmed_pdf)

def delete_job_files(job_id: str):
    """Securely deletes all temporary files associated with a job for privacy."""
    for p in UPLOADS_DIR.glob(f"{job_id}*"):
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass

def cleanup_old_uploads(max_age_minutes: int = 240):
    """
    Auto-purges uploaded customer files.
    - If job is already printed or cancelled: deletes after 15 minutes for customer privacy.
    - If job is still pending, waiting for merchant, or in print queue: retains file for 4 hours (240 minutes)
      so delayed payments or merchant approvals never suffer from missing file errors!
    """
    import time
    now = time.time()
    try:
        import database
    except ImportError:
        database = None

    for p in UPLOADS_DIR.iterdir():
        if p.is_file():
            try:
                age_minutes = (now - p.stat().st_mtime) / 60
                job_id = p.stem.replace("_trimmed", "")
                job = database.get_job(job_id) if database else None
                
                if job and job.get("print_status") in ["printed", "cancelled"]:
                    if age_minutes > 15:
                        p.unlink(missing_ok=True)
                elif age_minutes > max_age_minutes:
                    p.unlink(missing_ok=True)
            except Exception:
                pass

