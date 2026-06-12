import os


def detect_document_class(file_path: str, ocr_text: str = "") -> str:
    filename = os.path.basename(file_path).lower()
    text_lower = ocr_text.lower()
    combined = filename + " " + text_lower

    FORMAL_KEYWORDS = [
        "certificate", "marksheet", "degree",
        "diploma", "transcript", "result",
        "admit card", "identity", "passport",
        "licence", "license", "affidavit",
        "notary", "apostille", "registration"
    ]

    SYSTEM_KEYWORDS = [
        "boarding", "flight", "gate", "seat",
        "passenger", "airline", "airways",
        "ticket", "receipt", "invoice",
        "booking", "reservation", "itinerary",
        "voucher", "order", "payment", "bill",
        "statement", "transaction", "amount paid",
        "total", "subtotal", "gst", "tax invoice",
        "confirmation", "reference number",
        "pnr", "e-ticket", "barcode"
    ]

    formal_score = sum(
        1 for kw in FORMAL_KEYWORDS
        if kw in combined
    )
    system_score = sum(
        1 for kw in SYSTEM_KEYWORDS
        if kw in combined
    )

    if formal_score > system_score:
        return "formal"
    elif system_score > 0:
        return "system"
    else:
        return "unknown"
