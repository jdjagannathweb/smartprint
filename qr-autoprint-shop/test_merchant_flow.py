from pathlib import Path
from pypdf import PdfWriter
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)

def test_flow():
    print("\n--- 1. Creating sample file and uploading ---")
    test_pdf = Path("test_verify.pdf")
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    with open(test_pdf, "wb") as f:
        w.write(f)

    with open(test_pdf, "rb") as f:
        res = client.post("/api/upload", files={"file": ("test_verify.pdf", f, "application/pdf")})
    assert res.status_code == 200
    job = res.json()
    job_id = job["id"]
    print(f"Uploaded: {job_id}")

    print("\n--- 2. Customer clicks 'I Have Paid' (/api/jobs/{job_id}/customer-paid) ---")
    res = client.post(f"/api/jobs/{job_id}/customer-paid")
    assert res.status_code == 200
    res_data = res.json()
    job_state = res_data["job"]
    print(f"Payment Status: {job_state['payment_status']}")
    print(f"Print Status: {job_state['print_status']}")

    # VERIFY: MUST NOT BE PRINTED YET!
    assert job_state["payment_status"] == "claimed", "Must be 'claimed'!"
    assert job_state["print_status"] == "waiting_merchant", "Must wait for merchant approval!"
    print("SUCCESS: Direct printing is STOPPED! Document did NOT print on customer click.")

    print("\n--- 3. Merchant verifies payment and approves (/merchant-approve) ---")
    res = client.post(f"/api/jobs/{job_id}/merchant-approve")
    assert res.status_code == 200
    approved_job = res.json()["job"]
    print(f"After Merchant Approval: Payment={approved_job['payment_status']}, Print={approved_job['print_status']}")
    assert approved_job["payment_status"] == "paid"
    assert approved_job["print_status"] == "printing"
    print("SUCCESS: Print triggered ONLY after merchant approved!")

    test_pdf.unlink(missing_ok=True)
    print("\n=======================================================")
    print("  MERCHANT VERIFICATION TEST PASSED 100% PERFECTLY!   ")
    print("=======================================================\n")

if __name__ == "__main__":
    test_flow()
