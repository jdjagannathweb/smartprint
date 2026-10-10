import os
import sys
from pathlib import Path
from PIL import Image
from pypdf import PdfWriter
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def run_tests():
    print("\n--- 1. Testing Network Info & Counter QR ---")
    res = client.get("/api/network-info")
    assert res.status_code == 200, f"Failed: {res.text}"
    net_data = res.json()
    print(f"Detected Customer URL: {net_data['customer_url']}")
    assert net_data["customer_url"].startswith("http://")
    assert net_data["counter_qr"].startswith("data:image/png;base64,")
    print("SUCCESS: Network & Counter QR verified!")

    print("\n--- 2. Testing Settings & Printers ---")
    res = client.get("/api/settings")
    assert res.status_code == 200
    settings = res.json()
    print(f"Current Shop Name: {settings['shop_name']}, BW Rate: Rs {settings['rate_bw']}, Color: Rs {settings['rate_color']}")

    res = client.get("/api/printers")
    assert res.status_code == 200
    printers = res.json()
    print(f"Detected Printers count: {len(printers.get('printers', []))}")
    print(f"Default Printer: {printers.get('default')}")

    print("\n--- 3. Testing PDF Creation and Upload ---")
    test_pdf_path = Path("test_sample.pdf")
    writer = PdfWriter()
    for i in range(3):
        writer.add_blank_page(width=595, height=842)
    with open(test_pdf_path, "wb") as f:
        writer.write(f)

    with open(test_pdf_path, "rb") as f:
        res = client.post("/api/upload", files={"file": ("test_sample.pdf", f, "application/pdf")})
    assert res.status_code == 200, f"Upload error: {res.text}"
    job = res.json()
    job_id = job["id"]
    print(f"Uploaded Job ID: {job_id}, Total Pages: {job['total_pages']}")
    assert job["total_pages"] == 3

    print("\n--- 4. Testing Configuration & UPI Dynamic QR ---")
    res = client.post(f"/api/jobs/{job_id}/configure", json={
        "copies": 2,
        "color_mode": "color",
        "selected_pages": "all"
    })
    assert res.status_code == 200
    configured = res.json()
    print(f"Configured Bill: Rs {configured['total_amount']}, UPI URI: {configured['upi_uri']}")
    assert configured["total_amount"] == 60.0
    assert "upi://pay?" in configured["upi_uri"]
    assert "am=60.00" in configured["upi_uri"]
    assert configured["qr_code"].startswith("data:image/png;base64,")

    print("\n--- 5. Testing Payment Confirmation ---")
    res = client.post(f"/api/jobs/{job_id}/pay-confirm")
    assert res.status_code == 200
    pay_data = res.json()
    print(f"Payment Confirmed: {pay_data['job']['payment_status']}, Auto-Print: {pay_data['auto_print']}")
    assert pay_data["job"]["payment_status"] == "paid"

    print("\n--- 6. Testing Admin Stats & History ---")
    res = client.get("/api/admin/jobs")
    assert res.status_code == 200
    admin_data = res.json()
    print(f"Total Revenue: Rs {admin_data['stats']['total_revenue']}")
    print(f"Total Jobs in Queue: {admin_data['stats']['total_jobs']}")
    assert admin_data["stats"]["total_jobs"] >= 1

    test_pdf_path.unlink(missing_ok=True)
    print("\n=======================================================")
    print("  ALL SYSTEM TESTS PASSED PERFECTLY! 100% SUCCESSFUL   ")
    print("=======================================================\n")

if __name__ == "__main__":
    run_tests()
