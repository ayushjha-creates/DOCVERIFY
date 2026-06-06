import hashlib
import datetime
import json

def generate_document_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()

def create_blockchain_verification(file_path, analysis_results):
    doc_hash = generate_document_hash(file_path)
    score = analysis_results.get("scoring", {}).get("score", 0)
    status = analysis_results.get("scoring", {}).get("status", "unknown")

    block = {
        "document_hash": doc_hash,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "authenticity_score": score,
        "verdict": status,
        "previous_block_hash": "0000000000000000000000000000000000000000000000000000000000000000",
        "nonce": 0,
    }

    block_hash = hashlib.sha256(
        json.dumps(block, sort_keys=True).encode()
    ).hexdigest()

    verification_url = f"https://verify.docverify.io/check/{doc_hash[:16]}"

    return {
        "blockchain_hash": block_hash,
        "document_hash": doc_hash,
        "timestamp": block["timestamp"],
        "verification_url": verification_url,
        "block_number": 1,
    }
