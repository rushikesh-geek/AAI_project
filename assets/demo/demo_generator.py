"""
Demo document generator — creates synthetic PDF fixtures for demonstration.
"""
from __future__ import annotations

from pathlib import Path

def _create_pdf(content: str, output_path: Path) -> None:
    """Create a simple PDF using PyMuPDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    # Write text
    y = 50
    for line in content.split('\n'):
        if line.strip():
            font_size = 14 if line.startswith('===') else (12 if line.startswith('---') else 10)
            line = line.replace('===', '').replace('---', '').strip()
            if line:
                page.insert_text((50, y), line, fontsize=font_size, color=(0, 0, 0))
        y += 16
        if y > 800:
            page = doc.new_page(width=595, height=842)
            y = 50
    doc.save(str(output_path))
    doc.close()


INVOICE_TEXT = """=== SHREE TRADERS ===
GST Tax Invoice
---
GSTIN: 27AAACS1234A1Z5
Address: 123, Market Street, Mumbai, Maharashtra - 400001
Phone: +91 98765 43210

Invoice No: INV-0847
Invoice Date: 15/09/2024
Due Date: 15/10/2024
Purchase Order: PO-2024-0156

Bill To:
ABC Technologies Pvt Ltd
456, Tech Park, Pune - 411001
GSTIN: 27AABCA5678B1Z3

---
Item Description                    Qty    Rate (₹)    Amount (₹)
Office Furniture (Executive Desk)   5      4500.00     22500.00
Ergonomic Chairs                   10      1200.00     12000.00
Filing Cabinets                     3      2600.00      7800.00
---
Subtotal: Rs.42300.00
Total Amount: Rs.44300.00

Note: Stated total includes a known discrepancy for demonstration purposes.
Payment Terms: Net 30 days
Bank: State Bank of India | A/c: 1234567890 | IFSC: SBIN0001234
"""

KYC_TEXT = """=== SYNTHETIC IDENTITY DOCUMENT (DEMONSTRATION ONLY) ===
This is a fictitious document created for software demonstration.
Do NOT use as a real identity document.
---
Document Type: Passport
Document Number: Z9876543

Name: RAVI KUMAR SHARMA
Date of Birth: 12/05/1985
Nationality: Indian
Gender: Male
Address: 789, Green Colony, Bengaluru, Karnataka - 560001

Issue Date: 01/06/2019
Expiry Date: 31/05/2024

Issuing Authority: Ministry of External Affairs, Government of India
---
[Signature Present]  [Photo Present]
---
SYNTHETIC DEMO DOCUMENT — NOT A VALID GOVERNMENT ID
"""

KYC_VALID_TEXT = """=== SYNTHETIC IDENTITY DOCUMENT (DEMONSTRATION ONLY) ===
This is a fictitious document created for software demonstration.
---
Document Type: Aadhaar Card
Document Number: 1234 5678 9012

Name: PRIYA VERMA
Date of Birth: 22/08/1990
Nationality: Indian
Gender: Female
Address: 45, Rose Garden, Hyderabad, Telangana - 500032

Issue Date: 15/03/2020
Expiry Date: 14/03/2030

[Signature Present]  [Photo Present]
SYNTHETIC DEMO DOCUMENT — NOT A VALID GOVERNMENT ID
"""

CONTRACT_TEXT = """=== VENDOR SERVICES AGREEMENT ===
---
This Agreement is entered into on 01 April 2024 (Effective Date)

Between:
ABC Technologies Pvt Ltd, a company incorporated under Indian law
(hereinafter "Client")

And:
Shree Traders, a partnership firm
(hereinafter "Vendor")

---
1. SERVICES
The Vendor agrees to supply office furniture and equipment as per PO.

2. PAYMENT TERMS
Payment shall be made within 45 days of invoice receipt.
Note: Standard template requires 30-day payment terms.

3. TERMINATION
Either party may terminate this agreement with 15 days written notice.

4. CONFIDENTIALITY
Both parties shall maintain strict confidentiality of shared information
and proprietary business data disclosed during the contract period.

5. GOVERNING LAW
This agreement shall be governed by the laws of India.

6. LIABILITY
Total liability shall not exceed the contract value for the preceding 12 months.

7. FORCE MAJEURE
Neither party shall be liable for delays due to circumstances beyond reasonable control.

Effective Date: 01/04/2024
Expiry Date: 31/03/2025

Signed by both parties.
"""


def create_demo_documents(demo_dir: Path) -> dict[str, Path]:
    """Create demo PDF files. Returns {name: path} dict."""
    demo_dir.mkdir(parents=True, exist_ok=True)
    files = {}

    invoice_path = demo_dir / "demo_invoice_INV-0847.pdf"
    if not invoice_path.exists():
        _create_pdf(INVOICE_TEXT, invoice_path)
    files["invoice"] = invoice_path

    kyc_expired_path = demo_dir / "demo_kyc_expired.pdf"
    if not kyc_expired_path.exists():
        _create_pdf(KYC_TEXT, kyc_expired_path)
    files["kyc_expired"] = kyc_expired_path

    kyc_valid_path = demo_dir / "demo_kyc_valid.pdf"
    if not kyc_valid_path.exists():
        _create_pdf(KYC_VALID_TEXT, kyc_valid_path)
    files["kyc_valid"] = kyc_valid_path

    contract_path = demo_dir / "demo_contract_vendor.pdf"
    if not contract_path.exists():
        _create_pdf(CONTRACT_TEXT, contract_path)
    files["contract"] = contract_path

    return files
