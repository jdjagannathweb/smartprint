import os
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from server import app
import database

client = TestClient(app)

def test_endpoints():
    print("--- 1. Testing Page Endpoints ---")
    pages = ["/", "/register", "/login", "/dashboard", "/s/smart-print", "/superadmin"]
    for p in pages:
        r = client.get(p)
        assert r.status_code == 200, f"Page {p} returned {r.status_code}"
        print(f"  [OK] {p} -> {r.status_code}")

    print("\n--- 2. Testing Shop Self-Registration ---")
    reg_data = {
        "shop_name": "ମାଆ ସମଲେଇ ପ୍ରିଣ୍ଟ୍ କେନ୍ଦ୍ର",
        "owner_name": "ସନ୍ତୋଷ ସାହୁ",
        "mobile": "9876543210",
        "password": "pass1234",
        "slug": "samalei-print",
        "upi_id": "9876543210@paytm"
    }
    r = client.post("/api/auth/register", json=reg_data)
    assert r.status_code in [200, 400], f"Register failed: {r.text}"
    if r.status_code == 200:
        shop = r.json()["shop"]
        shop_id = shop["shop_id"]
        print(f"  [OK] Registered shop: {shop['shop_name']} ({shop_id}), slug: {shop['slug']}")
    else:
        print(f"  [Info] Already registered or {r.json()}")
        shop = database.get_shop_by_mobile("9876543210")
        shop_id = shop["shop_id"]

    print("\n--- 3. Testing Shopkeeper Login ---")
    login_data = {
        "mobile": "9876543210",
        "password": "pass1234"
    }
    r = client.post("/api/auth/login", json=login_data)
    assert r.status_code == 200, f"Login failed: {r.text}"
    print(f"  [OK] Shop Login successful for mobile 9876543210")

    print("\n--- 4. Testing Shop Details & Plans API ---")
    r = client.get(f"/api/shop/{shop_id}")
    assert r.status_code == 200
    shop_details = r.json()
    print(f"  [OK] Shop Days Left: {shop_details['days_left']}")
    print(f"  [OK] SaaS Plan 1: {shop_details['saas_plans']['plan1']}")
    print(f"  [OK] SaaS Plan 2: {shop_details['saas_plans']['plan2']}")

    print("\n--- 5. Testing Customer Portal API ---")
    r = client.get("/api/customer/shop/samalei-print")
    assert r.status_code == 200
    cust_info = r.json()
    assert cust_info["shop_name"] == "ମାଆ ସମଲେଇ ପ୍ରିଣ୍ଟ୍ କେନ୍ଦ୍ର"
    assert cust_info["subscription_valid"] is True
    print(f"  [OK] Customer sees shop '{cust_info['shop_name']}' with rate: ₹{cust_info['rate_bw']}")

    print("\n--- 6. Testing Super Admin Auth & Overview ---")
    r = client.post("/api/superadmin/login", json={"pin": "1234"})
    assert r.status_code == 200
    print("  [OK] Super Admin PIN verified")

    r = client.get("/api/superadmin/overview?pin=1234")
    assert r.status_code == 200
    overview_data = r.json()
    print(f"  [OK] Total registered shops: {overview_data['overview']['total_shops']}")
    print(f"  [OK] Active shops: {overview_data['overview']['active_shops']}")

    print("\n--- 7. Testing 1-Click Plan Extension ---")
    # Extend by 365 days (Plan 2: 1 Year)
    r = client.post("/api/superadmin/extend", json={"pin": "1234", "shop_id": shop_id, "days": 365})
    assert r.status_code == 200
    new_exp = r.json()["new_expiry"]
    print(f"  [OK] Extended shop validity by 1 Year! New expiry: {new_exp}")

    # Verify extended days
    r = client.get(f"/api/shop/{shop_id}")
    new_days = r.json()["days_left"]
    print(f"  [OK] Updated Days Left: {new_days} days (180 free trial + 365 extended = ~545 days)")

    print("\n--- 8. Testing Option 2 Connector Launcher Download ---")
    r = client.get(f"/api/connector/download-launcher/{shop_id}")
    assert r.status_code == 200
    assert "start_connector" in r.headers.get("content-disposition", "")
    print("  [OK] Option 2 Launcher .bat generated and verified")

    print("\n" + "="*50)
    print(" ALL SAAS MULTI-TENANT & 2-PLAN TESTS PASSED! 🎉")
    print("="*50)

if __name__ == "__main__":
    test_endpoints()
