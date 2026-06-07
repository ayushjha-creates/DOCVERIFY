WARN_POINTS = {
    "metadata": 10,
    "ocr": 10,
    "qr": 15,
    "tampering": 20,
    "signature": 10,
}

FAIL_POINTS = {
    "metadata": 20,
    "ocr": 20,
    "qr": 30,
    "tampering": 35,
    "signature": 15,
}

# Fail engines with score >= this threshold get full fail deduction
_FULL_FAIL_THRESHOLD = 0.7


def _score_to_status(score):
    if score >= 85:
        return "genuine"
    elif score >= 60:
        return "suspicious"
    else:
        return "tampered"


def _engine_severity(val):
    if not val:
        return "clean"
    s = val.get("status", "")
    if s in ("tampered", "fail", "error"):
        return "fail"
    if s in ("suspicious", "warn"):
        return "warn"
    return "clean"


def _duplicate_penalty(findings_map):
    """Detect actual duplicate/redundant findings by normalized title."""
    from collections import Counter
    titles = []
    for key, findings in findings_map.items():
        if not findings:
            continue
        for f in findings:
            t = f.get("title", "").strip().lower()
            if t and f.get("points", 0) > 0:
                titles.append(t)
    dup_count = sum(c - 1 for c in Counter(titles).values() if c > 1)
    if dup_count >= 4:
        return 25
    if dup_count >= 2:
        return 10
    return 0


def calculate_score(results):
    deductions = {"metadata": 0, "ocr": 0, "qr": 0, "tampering": 0, "signature": 0}
    reasons = []

    metadata = results.get("metadata", {})
    ocr = results.get("ocr", {})
    qr = results.get("qr", {})
    tampering = results.get("tampering", {})
    signature = results.get("signature", {})

    engines = [
        ("metadata", metadata, WARN_POINTS["metadata"], FAIL_POINTS["metadata"]),
        ("ocr", ocr, WARN_POINTS["ocr"], FAIL_POINTS["ocr"]),
        ("qr", qr, WARN_POINTS["qr"], FAIL_POINTS["qr"]),
        ("tampering", tampering, WARN_POINTS["tampering"], FAIL_POINTS["tampering"]),
        ("signature", signature, WARN_POINTS["signature"], FAIL_POINTS["signature"]),
    ]

    fail_count = 0
    warn_count = 0

    for name, val, warn_pts, fail_pts in engines:
        if not val or "score" not in val:
            continue
        raw = val["score"]
        severity = _engine_severity(val)

        if severity == "fail":
            fail_count += 1
            deduction = min(abs(raw), fail_pts)
        elif severity == "warn":
            warn_count += 1
            deduction = min(abs(raw), warn_pts)
        elif raw < 0:
            deduction = min(abs(raw), warn_pts)
        else:
            deduction = 0

        deductions[name] = deduction

    # ── Signature exception: "no_signature" is clean, no deduction ──
    sig_status = signature.get("status", "") if signature else ""
    if sig_status == "no_signature":
        deductions["signature"] = 0
        if fail_count > 0:
            fail_count -= 1

    # ── FAIL multiplier (capped so multiplied deduction never exceeds fail_pts) ──
    multiplier = 1.0
    if fail_count == 1:
        multiplier = 1.3
    elif fail_count == 2:
        multiplier = 1.6
    elif fail_count >= 3:
        multiplier = 2.0

    if multiplier > 1.0:
        for name, val, _, fail_pts in engines:
            if _engine_severity(val) == "fail":
                multiplied = int(deductions[name] * multiplier)
                deductions[name] = min(multiplied, fail_pts)
        reasons.append(f"FAIL severity penalty (×{multiplier})")

    # ── Co‑occurrence: one flat penalty for 3+ engines with deductions ──
    active_engines = sum(1 for v in deductions.values() if v > 0)
    co_penalty = 10 if active_engines >= 3 else 0

    # ── True duplicate penalty (same title repeated across findings) ──
    findings_map = {k: results.get(k, {}).get("findings", []) for k in ("metadata", "ocr", "qr", "tampering", "signature")}
    dup_penalty = _duplicate_penalty(findings_map)

    total_deduction = sum(deductions.values()) + co_penalty + dup_penalty

    for name, label, pts in [
        ("metadata", "Metadata issues", deductions["metadata"]),
        ("ocr", "Text/OCR anomalies", deductions["ocr"]),
        ("qr", "QR code concerns", deductions["qr"]),
        ("tampering", "Tampering evidence detected", deductions["tampering"]),
        ("signature", "Signature/stamp irregularities", deductions["signature"]),
    ]:
        if pts > 0:
            reasons.append(f"{label} (-{pts} pts)")
    if co_penalty > 0:
        reasons.append(f"Co-occurring issue types (-{co_penalty} pts)")
    if dup_penalty > 0:
        reasons.append(f"Redundant findings (-{dup_penalty} pts)")

    final_score = max(0, 100 - total_deduction)
    status = _score_to_status(final_score)

    return {
        "score": final_score,
        "status": status,
        "deductions": deductions,
        "total_deduction": total_deduction,
        "reasons": reasons,
    }
