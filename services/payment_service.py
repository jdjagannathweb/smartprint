import io
import re
import base64
import urllib.parse
import qrcode
from PIL import Image

def clean_ascii_text(text: str, fallback: str = "Smart Print") -> str:
    """Removes non-ASCII characters so UPI apps do not reject the intent."""
    if not text:
        return fallback
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", "", text).strip()
    return cleaned if cleaned else fallback

def generate_upi_uri(upi_id: str, merchant_name: str, amount: float, order_id: str, note: str = "Print") -> str:
    """
    Constructs a 100% NPCI compliant UPI Intent URI.
    Format: upi://pay?pa=...&pn=...&am=...&cu=INR&tn=...&mode=02
    NO non-ASCII chars in pn, NO hash (#) or special characters in tn.
    """
    clean_vpa = upi_id.strip()
    clean_pn = clean_ascii_text(merchant_name, "Smart Print")
    clean_tn = f"Order_{re.sub(r'[^a-zA-Z0-9]', '', order_id)}"

    params = [
        ("pa", clean_vpa),
        ("pn", clean_pn),
        ("am", f"{amount:.2f}"),
        ("cu", "INR"),
        ("tn", clean_tn),
        ("mode", "02")
    ]
    query_string = urllib.parse.urlencode(params)
    return f"upi://pay?{query_string}"

def generate_paytm_upi_uri(paytm_vpa: str, merchant_name: str, amount: float, order_id: str) -> str:
    """
    Constructs a Paytm Business compliant UPI Intent URI.
    Matches Paytm merchant transaction routing with &tr= and &tn= parameter binding.
    """
    clean_vpa = paytm_vpa.strip()
    clean_pn = clean_ascii_text(merchant_name, "Smart Print")
    clean_id = re.sub(r'[^a-zA-Z0-9]', '', order_id)

    params = [
        ("pa", clean_vpa),
        ("pn", clean_pn),
        ("am", f"{amount:.2f}"),
        ("cu", "INR"),
        ("tn", f"TXN_{clean_id}"),
        ("tr", clean_id),
        ("mode", "02")
    ]
    query_string = urllib.parse.urlencode(params)
    return f"upi://pay?{query_string}"

def check_paytm_order_status(mid: str, merchant_key: str, order_id: str) -> dict:
    """
    Calls Paytm Official v3 Order Status API.
    Zero-commission verification directly against Paytm Merchant core.
    Returns: {"success": True/False, "status": "TXN_SUCCESS"|"PENDING"|"TXN_FAILURE", "txn_id": str}
    """
    import json
    import urllib.request
    try:
        from paytmchecksum import PaytmChecksum
    except ImportError:
        return {"success": False, "status": "ERROR", "error": "PaytmChecksum module not installed"}

    clean_order_id = re.sub(r'[^a-zA-Z0-9]', '', order_id)
    paytm_params = {
        "body": {
            "mid": mid.strip(),
            "orderId": clean_order_id
        }
    }
    
    try:
        body_str = json.dumps(paytm_params["body"])
        checksum = PaytmChecksum.generateSignature(body_str, merchant_key.strip())
        paytm_params["head"] = {"signature": checksum}
        
        post_data = json.dumps(paytm_params).encode("utf-8")
        url = "https://securegw.paytm.in/v3/order/status"
        
        req = urllib.request.Request(
            url,
            data=post_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "SmartPrintPaytm/1.0"
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_raw = response.read().decode("utf-8")
            data = json.loads(res_raw)
            body = data.get("body", {})
            res_info = body.get("resultInfo", {})
            res_status = res_info.get("resultStatus", "")
            
            is_success = (res_status == "TXN_SUCCESS")
            return {
                "success": is_success,
                "status": res_status,
                "txn_id": body.get("txnId") or body.get("bankTxnId") or "",
                "amount": body.get("txnAmount", "0.00"),
                "message": res_info.get("resultMsg", ""),
                "raw": body
            }
    except Exception as e:
        return {"success": False, "status": "ERROR", "error": str(e)}

def generate_qr_base64(data_url: str, box_size: int = 10, border: int = 2) -> str:
    """Generates a high-contrast base64 encoded PNG image for the given URL/data."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border
    )
    qr.add_data(data_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"

def generate_counter_qr(base_url: str) -> str:
    """Generates the QR code for customers to scan at the counter."""
    return generate_qr_base64(base_url, box_size=12, border=3)

def initiate_phonepe_checkout(
    client_id: str,
    client_secret: str,
    client_version: int = 1,
    env_str: str = "PRODUCTION",
    amount: float = 1.0,
    order_id: str = "",
    redirect_url: str = ""
) -> dict:
    """
    Initiates a PhonePe Standard Checkout V2 payment.
    Uses official phonepe-pg-sdk-python as taught in PhonePe Standard Checkout developer tutorial.
    Returns: {"success": bool, "redirect_url": str, "order_id": str, "state": str, "error": str}
    """
    try:
        from phonepe.sdk.pg.payments.v2.standard_checkout_client import StandardCheckoutClient
        from phonepe.sdk.pg.env import Env
        from phonepe.sdk.pg.payments.v2.models.request.standard_checkout_pay_request import StandardCheckoutPayRequest
    except ImportError:
        return {"success": False, "error": "phonepe-pg-sdk-python not installed"}

    try:
        env = Env.SANDBOX if (env_str or "").strip().upper() == "SANDBOX" else Env.PRODUCTION
        client = StandardCheckoutClient.get_instance(
            client_id=client_id.strip(),
            client_secret=client_secret.strip(),
            client_version=int(client_version or 1),
            env=env
        )

        amount_paisa = max(100, int(round(amount * 100)))
        clean_order_id = re.sub(r'[^a-zA-Z0-9_-]', '', order_id)
        if not clean_order_id:
            clean_order_id = f"ORDER_{int(amount * 100)}"

        pay_request = StandardCheckoutPayRequest.build_request(
            merchant_order_id=clean_order_id,
            amount=amount_paisa,
            redirect_url=redirect_url or "https://smartprint.in"
        )
        pay_res = client.pay(pay_request)

        return {
            "success": True,
            "redirect_url": pay_res.redirect_url,
            "order_id": pay_res.order_id or clean_order_id,
            "state": pay_res.state or "PENDING"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_phonepe_order_status(
    client_id: str,
    client_secret: str,
    client_version: int = 1,
    env_str: str = "PRODUCTION",
    order_id: str = ""
) -> dict:
    """
    Queries PhonePe Standard Checkout Order Status API.
    Returns: {"success": bool, "status": "COMPLETED"|"PENDING"|"FAILED"|"ERROR", "order_id": str, "amount": float, "message": str}
    """
    try:
        from phonepe.sdk.pg.payments.v2.standard_checkout_client import StandardCheckoutClient
        from phonepe.sdk.pg.env import Env
    except ImportError:
        return {"success": False, "status": "ERROR", "error": "phonepe-pg-sdk-python not installed"}

    try:
        env = Env.SANDBOX if (env_str or "").strip().upper() == "SANDBOX" else Env.PRODUCTION
        client = StandardCheckoutClient.get_instance(
            client_id=client_id.strip(),
            client_secret=client_secret.strip(),
            client_version=int(client_version or 1),
            env=env
        )

        clean_order_id = re.sub(r'[^a-zA-Z0-9_-]', '', order_id)
        status_res = client.get_order_status(clean_order_id)

        # PhonePe Standard Checkout states: COMPLETED, PENDING, FAILED
        state = (status_res.state or "PENDING").upper()
        is_success = (state == "COMPLETED")
        amount_in_rupees = (status_res.amount / 100.0) if status_res.amount else 0.0

        return {
            "success": is_success,
            "status": state,
            "order_id": status_res.order_id or clean_order_id,
            "amount": amount_in_rupees,
            "message": status_res.detailed_error_code or status_res.error_code or ""
        }
    except Exception as e:
        return {"success": False, "status": "ERROR", "error": str(e)}

def create_smbupi_order(
    api_key: str,
    api_secret: str,
    amount: float,
    order_id: str,
    callback_url: str = "",
    customer_name: str = "SmartPrint Customer",
    customer_mobile: str = "9999999999",
    description: str = "SmartPrint Document"
) -> dict:
    """
    Creates an SMB UPI (smbupi.com) payment order.
    Returns: {"success": bool, "payment_url": str, "order_id": str, "token": str, "error": str}
    """
    import json
    import urllib.request

    clean_order_id = re.sub(r'[^a-zA-Z0-9_-]', '', order_id)
    payload = {
        "amount": f"{amount:.2f}",
        "order_id": clean_order_id,
        "customer_name": clean_ascii_text(customer_name, "Customer"),
        "customer_mobile": customer_mobile or "9999999999",
        "description": clean_ascii_text(description, "Print Order"),
        "callback_url": callback_url or ""
    }

    try:
        req = urllib.request.Request(
            "https://smbupi.com/api/create-order",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key.strip(),
                "X-API-Secret": api_secret.strip(),
                "User-Agent": "SmartPrint/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("status") == "success":
                data = res_data.get("data", {})
                return {
                    "success": True,
                    "payment_url": data.get("payment_url", ""),
                    "order_id": data.get("order_id", clean_order_id),
                    "token": data.get("token", "")
                }
            return {
                "success": False,
                "error": res_data.get("error") or res_data.get("message") or "Failed to create SMB UPI order"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_smbupi_order_status(api_key: str, api_secret: str, order_id: str) -> dict:
    """
    Checks order status against SMB UPI (smbupi.com) Check Status API.
    Returns: {"success": bool, "status": "success"|"pending"|"failed"|"error", "order_id": str, "utr": str, "amount": float, "error": str}
    """
    import json
    import urllib.request

    clean_order_id = re.sub(r'[^a-zA-Z0-9_-]', '', order_id)
    payload = {
        "order_id": clean_order_id
    }

    try:
        req = urllib.request.Request(
            "https://smbupi.com/api/check-status",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key.strip(),
                "X-API-Secret": api_secret.strip(),
                "User-Agent": "SmartPrint/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("status") == "success":
                data = res_data.get("data", {})
                payment_status = (data.get("payment_status") or "").lower()
                is_success = (payment_status == "success")
                return {
                    "success": is_success,
                    "status": payment_status or "pending",
                    "order_id": data.get("order_id", clean_order_id),
                    "utr": data.get("utr", ""),
                    "amount": float(data.get("amount") or 0.0)
                }
            return {
                "success": False,
                "status": "error",
                "error": res_data.get("error") or res_data.get("message") or "Failed to query SMB UPI order status"
            }
    except Exception as e:
        return {"success": False, "status": "error", "error": str(e)}
