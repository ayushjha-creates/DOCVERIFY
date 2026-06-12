ENGINE_KEYS = ["metadata", "ocr", "qr", "tamper", "signature"]
ENGINE_LABELS = {
    "metadata": "metadata",
    "ocr": "ocr",
    "qr": "qr",
    "tamper": "tampering",
    "signature": "signature",
}

MODULE_WEIGHTS = {
    "metadata": 1.5,
    "ocr": 0.3,
    "qr": 1.5,
    "tamper": 0.5,
    "signature": 1.0,
}

FINDING_PENALTIES = {
    "info": 2,
    "warning": 5,
    "error": 15,
}

MAX_MODULE_DEDUCTION = 50


def calculate_module_score(findings: list) -> dict:
    if not findings:
        return {"score": 100, "deduction": 0, "total_penalty": 0}

    total_penalty = 0
    for f in findings:
        points = f.get("points", 0)
        if points > 0:
            total_penalty += points

    total_penalty = min(total_penalty, MAX_MODULE_DEDUCTION)
    module_score = max(0, 100 - total_penalty)

    return {
        "score": module_score,
        "deduction": total_penalty,
        "total_penalty": total_penalty,
    }


def compute_ai_likelihood(findings: dict) -> float:
    all_items = []
    for module_findings in findings.values():
        all_items.extend(module_findings)

    signals = []

    for f in all_items:
        title = f.get("title", "").lower()
        detail = f.get("detail", "").lower()

        if "unnatural text uniformity" in title:
            signals.append(0.4)
        elif "overly consistent text" in title:
            signals.append(0.3)
        elif "ai-generated text pattern" in title:
            signals.append(0.6)
        elif "ai tool detected" in title:
            signals.append(0.3)
        elif "ai image generator" in title:
            signals.append(0.3)
        elif "missing producer metadata" in title:
            signals.append(0.15)
        elif "low character diversity" in title:
            signals.append(0.3)

    meta_findings = findings.get("metadata", [])
    ocr_findings = findings.get("ocr", [])

    has_text_anomalies = any(
        "uniform" in f.get("title", "").lower()
        or "consistent" in f.get("title", "").lower()
        for f in ocr_findings
    )
    if has_text_anomalies:
        signals.append(0.25)

    has_no_metadata = any(
        "no creator/producer" in f.get("detail", "").lower()
        or "no exif data" in f.get("detail", "").lower()
        for f in meta_findings
    )
    if has_no_metadata and any("ai" in f.get("title", "").lower() for f in ocr_findings):
        signals.append(0.2)

    if not signals:
        return 0.0

    score = min(1.0, sum(signals) / max(len(signals), 1) * 1.4)
    return round(score, 2)


def calculate_final_score(engine_results: dict, has_duplicate: bool, findings: dict = None, doc_class="unknown") -> dict:
    print("RAW ENGINE RESULTS RECEIVED:")
    for key, val in engine_results.items():
        print(f"  {key}:")
        print(f"    status    = {val.get('status')}")
        print(f"    deduction = {val.get('deduction')}")
        print(f"    keys      = {list(val.keys())}")
    print(f"  doc_class = {doc_class}")

    findings = findings or {}
    module_scores = {}
    total_weighted = 0.0
    total_weight = 0.0
    raw_deductions_total = 0

    # ── AI-flag forgiveness for system-class documents ──
    if doc_class == "system":
        tamper_findings_list = findings.get("tampering", [])
        tamper_titles = [f.get("title", "") for f in tamper_findings_list if f.get("points", 0) > 0]
        non_ai_titles = [t for t in tamper_titles if not t.startswith("AI:")]
        tamper_data = engine_results.get("tamper", {})
        if tamper_data.get("deduction", 0) > 0 and len(non_ai_titles) == 0 and len(tamper_titles) > 0:
            engine_results["tamper"]["deduction"] = 0
            engine_results["tamper"]["status"] = "OK"
            print(f"[scoring] System doc: AI-only tamper flags forgiven ({tamper_titles})")

    for ek in ENGINE_KEYS:
        label = ENGINE_LABELS.get(ek, ek)
        weight = MODULE_WEIGHTS.get(ek, 1.0)

        # Read deduction directly from engine_results (single source of truth)
        engine_deduct = int(engine_results.get(ek, {}).get("deduction") or 0)
        module_score = max(0, 100 - engine_deduct)

        module_scores[label] = {
            "score": module_score,
            "deduction": engine_deduct,
            "weight": weight,
        }

        total_weighted += module_score * weight
        total_weight += weight
        raw_deductions_total += engine_deduct

    base_score = round(total_weighted / total_weight) if total_weight > 0 else 0

    anomaly_count = sum(1 for info in module_scores.values() if info["deduction"] > 0)

    ai_likelihood = compute_ai_likelihood(findings)

    total_deductions = raw_deductions_total
    final_score = max(0, base_score - total_deductions)

    if anomaly_count >= 3:
        scaling = 0.6
    elif anomaly_count == 2:
        scaling = 0.75
    else:
        scaling = 0.9

    final_score = max(0, round(final_score * scaling))

    # Determine verdict
    if anomaly_count <= 1:
        verdict = "Genuine"
    elif final_score >= 50:
        verdict = "Suspicious"
    else:
        verdict = "Tampered"

    # Verification assertion
    total_possible_deduction = 20 + 20 + 30 + 35 + 15
    base_deduction = total_deductions
    assert 0 <= base_deduction <= total_possible_deduction, \
        f"base_deduction {base_deduction} out of range [0, {total_possible_deduction}]"
    assert 0 <= final_score <= 100, \
        f"final_score {final_score} out of range"
    assert verdict in ("Genuine", "Suspicious", "Tampered"), \
        f"verdict '{verdict}' invalid"

    print(f"SCORE VERIFICATION PASSED: {final_score} {verdict}")

    per_module_deductions = {}
    for label, info in module_scores.items():
        per_module_deductions[label] = info["deduction"]

    reasons = []
    for label, info in module_scores.items():
        if info["deduction"] > 0:
            reasons.append(f"{label.capitalize()} anomalies detected")

    if ai_likelihood > 0.7:
        reasons.append("AI-Generated Likely")

    print("=" * 45)
    print("SCORE BREAKDOWN")
    print("=" * 45)
    for label, info in module_scores.items():
        print(f"  {label:12} score={info['score']:3} deduction={info['deduction']:2} weight={info['weight']}")
    print(f"  Base score         : {base_score}")
    print(f"  Total deductions   : {total_deductions}")
    print(f"  Anomaly count      : {anomaly_count}")
    print(f"  AI likelihood      : {ai_likelihood}")
    print(f"  Scaling factor     : {scaling}")
    print(f"  Final score        : {final_score}")
    print(f"  Verdict            : {verdict}")
    print("=" * 45)

    return {
        "score": final_score,
        "verdict": verdict,
        "base_score": base_score,
        "total_deductions": total_deductions,
        "anomaly_count": anomaly_count,
        "ai_likelihood_score": ai_likelihood,
        "deductions": per_module_deductions,
        "reasons": reasons,
        "breakdown": {
            "module_scores": module_scores,
            "dedup_penalty": 40 if has_duplicate else 0,
            "total_deduction": total_deductions,
            "scaling_factor": scaling,
        },
    }
