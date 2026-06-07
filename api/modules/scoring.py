ENGINE_KEYS = ["metadata", "ocr", "qr", "tamper", "signature"]

MAX_DEDUCTIONS = {
    "metadata": 20, "ocr": 20,
    "qr": 30, "tamper": 35, "signature": 15,
}

CO_OCCURRENCE_PENALTIES = {
    0: 0, 1: 0, 2: 10, 3: 20, 4: 30, 5: 45,
}


def _map_status(status):
    if status in ("FAIL", "tampered", "fail", "error"):
        return "FAIL"
    if status in ("WARN", "suspicious", "warn"):
        return "WARN"
    return "OK"


def calculate_final_score(engine_results: dict, has_duplicate: bool) -> dict:
    base_deduction = 0
    engine_statuses = {}
    engine_deductions = {}

    for key in ENGINE_KEYS:
        engine = engine_results.get(key, {})
        status = _map_status(engine.get("status", "OK"))
        deduct = engine.get("deduction", 0)

        deduct = min(deduct, MAX_DEDUCTIONS.get(key, 20))
        deduct = max(deduct, 0)

        engine_statuses[key] = status
        engine_deductions[key] = deduct
        base_deduction += deduct

    # Co-occurrence
    fired = [k for k, s in engine_statuses.items() if s in ("WARN", "FAIL")]
    fired_count = len(fired)
    cooccurrence_penalty = CO_OCCURRENCE_PENALTIES.get(fired_count, 45)

    # Fail multiplier
    fail_engines = [k for k, s in engine_statuses.items() if s == "FAIL"]
    fail_count = len(fail_engines)

    pre_multiply = base_deduction + cooccurrence_penalty

    if fail_count == 0:
        multiplier = 1.0
    elif fail_count == 1:
        multiplier = 1.3
    elif fail_count == 2:
        multiplier = 1.6
    else:
        multiplier = 2.0

    multiplied_deduction = pre_multiply * multiplier

    # Duplicate penalty
    duplicate_penalty = 40 if has_duplicate else 0

    # Total
    total_deduction = multiplied_deduction + duplicate_penalty
    total_deduction = round(total_deduction)

    raw_score = 100 - total_deduction
    final_score = max(0, min(100, raw_score))

    # Hard caps
    if fail_count >= 1 and final_score > 55:
        final_score = 55
    if fail_count >= 2 and final_score > 35:
        final_score = 35
    if fail_count >= 3 and final_score > 20:
        final_score = 20
    if has_duplicate and final_score > 25:
        final_score = 25

    if final_score >= 85:
        verdict = "CLEAN"
    elif final_score >= 60:
        verdict = "SUSPICIOUS"
    else:
        verdict = "TAMPERED"

    # Debug
    print("=" * 45)
    print("SCORE BREAKDOWN")
    print("=" * 45)
    for k in ENGINE_KEYS:
        print(f"  {k:12} status={engine_statuses[k]:8} deduction={engine_deductions[k]}")
    print(f"  Base deduction      : {base_deduction}")
    print(f"  Engines fired       : {fired_count} {fired}")
    print(f"  Co-occurrence +     : {cooccurrence_penalty}")
    print(f"  Pre-multiply total  : {pre_multiply}")
    print(f"  Fail count          : {fail_count}")
    print(f"  Multiplier          : {multiplier}x")
    print(f"  Multiplied deduction: {round(multiplied_deduction)}")
    print(f"  Duplicate penalty   : {duplicate_penalty}")
    print(f"  Total deduction     : {total_deduction}")
    print(f"  Raw score           : {raw_score}")
    print(f"  Final score (capped): {final_score}")
    print(f"  Verdict             : {verdict}")
    print("=" * 45)

    return {
        "score": final_score,
        "verdict": verdict,
        "breakdown": {
            "base_deduction": base_deduction,
            "cooccurrence_penalty": cooccurrence_penalty,
            "fail_multiplier": multiplier,
            "duplicate_penalty": duplicate_penalty,
            "total_deduction": total_deduction,
            "engines_fired": fired,
            "fail_engines": fail_engines,
        },
    }
