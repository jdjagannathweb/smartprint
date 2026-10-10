# 🖨️ Smart Print Cloud - Multi-Tenant Auto Print Platform

A complete QR-based Self-Service Document Printing SaaS platform designed for Xerox and Cyber Cafe shops. Customers scan a QR code, upload documents from mobile, pay via UPI, and the merchant approves to silently print on their local printer.

## ✨ Features
- **2 Subscription Plans**: 6 Months (180 Days Free Trial / ₹499 Renewal) & 1 Year (₹899 Super Saver)
- **Isolated Shop Portals**: Every shopkeeper gets their own URL `/s/{slug}`
- **Shopkeeper Dashboard**: Real-time queue, price configuration, custom UPI & standee QR setup
- **Super Admin Panel**: Monitor all registered shops, track activity (jobs & pages printed), 1-click plan extension (+6M / +1Y)
- **Option 2 Print Connector**: 1-click silent background printing directly to local Windows printers via SumatraPDF
- **Fraud Proof**: Customer "Payment Done" requires merchant approval before physical paper prints
- **Odia & Multilingual UI**: Fully localized interface in Odia (`ଓଡ଼ିଆ`)

## 🚀 How to Run
```bash
pip install -r requirements.txt
python server.py
```

- **Landing Page**: `http://localhost:8000/`
- **Shop Registration**: `http://localhost:8000/register`
- **Shopkeeper Dashboard**: `http://localhost:8000/dashboard`
- **Super Admin**: `http://localhost:8000/superadmin` (Default PIN: `1234`)
