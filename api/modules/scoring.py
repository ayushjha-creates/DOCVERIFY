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


def _score_to_status(score):
    if score >= 85:
        return "genuine"
    elif score >= 60:
        return "suspicious"
    else:
        return "tampered"


def _positive_findings(results):
    count = 0
    for key in ("metadata", "ocr", "qr", "tampering", "signature"):
        val = results.get(key, {})
        if val and val.get("findings"):
            for f in val["findings"]:
                if f.get("severity") in ("high", "medium") and f.get("points", 0) > 0:
                    count += 1
    return count


def _engine_severity(val):
    if not val:
        return "clean"
    s = val.get("status", "")
    if s in ("tampered", "fail", "error"):
        return "fail"
    if s in ("suspicious", "warn"):
        return "warn"
    return "clean"


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

    # ── FAIL multiplier (only multiplies the FAIL engine's deduction) ──
    multiplier = 1.0
    if fail_count == 1:
        multiplier = 1.3
    elif fail_count == 2:
        multiplier = 1.6
    elif fail_count >= 3:
        multiplier = 2.0

    if multiplier > 1.0:
        for name, val, _, _ in engines:
            if _engine_severity(val) == "fail":
                deductions[name] = int(deductions[name] * multiplier)

    # ── Co-occurrence penalty (only triggers on 2+ distinct engines with deductions) ──
    active_engines = sum(1 for v in deductions.values() if v > 0)
    co_penalty = 0
    if active_engines >= 5:
        co_penalty = 45
    elif active_engines >= 4:
        co_penalty = 30
    elif active_engines >= 3:
        co_penalty = 20
    elif active_engines >= 2:
        co_penalty = 10

    # ── Duplicate deduction ──
    pos_count = _positive_findings(results)
    dup_penalty = 0
    if pos_count >= 8:
        dup_penalty = 40
    elif pos_count >= 5:
        dup_penalty = 25
    elif pos_count >= 3:
        dup_penalty = 10

    total_deduction = sum(deductions.values()) + co_penalty + dup_penalty

    if multiplier > 1.0:
        reasons.append(f"FAIL multiplier (×{multiplier}) applied to engines with FAIL status")

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
        reasons.append(f"Multiple issue types detected (-{co_penalty} pts co-occurrence penalty)")
    if dup_penalty > 0:
        reasons.append(f"Duplicate/redundant findings (-{dup_penalty} pts)")

    final_score = max(0, 100 - total_deduction)
    status = _score_to_status(final_score)

    return {
        "score": final_score,
        "status": status,
        "deductions": deductions,
        "total_deduction": total_deduction,
        "reasons": reasons,
    }
