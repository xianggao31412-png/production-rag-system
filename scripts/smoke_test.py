#!/usr/bin/env python
"""
End-to-end smoke test.

Boots the application in-process (no server, no network), ingests the bundled
example documents, runs a few representative queries, and verifies the admin /
dashboard surfaces respond. Exits non-zero on any failure so it can gate CI.

    python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Make the project root importable when run as `python scripts/smoke_test.py`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

EXAMPLES = ROOT / "demo" / "examples"
QUESTIONS = [
    ("How many vacation days do full-time employees get?", "company_policy.txt"),
    ("How do I reset my password?", "product_faq.md"),
    ("Where is Grace Hopper located?", "employees.csv"),
    ("What are the support hours?", "product_faq.md"),
]


def main() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        status = "ok " if condition else "FAIL"
        print(f"  [{status}] {label}{(' — ' + detail) if detail else ''}")
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            data_dir=tmp,
            llm_force_stub=True,
            require_auth=False,
            rate_limit_enabled=False,
            log_level="WARNING",
            log_json=False,
        )
        app = create_app(settings)
        with TestClient(app) as client:
            print("· health & readiness")
            check("health 200", client.get("/health").status_code == 200)
            ready = client.get("/ready").json()
            check("ready true", ready.get("ready") is True,
                  ", ".join(f"{c['name']}={c['ok']}" for c in ready["components"]))

            print("· ingest example corpus")
            for path in sorted(EXAMPLES.iterdir()):
                data = path.read_bytes()
                r = client.post("/v1/documents?namespace=demo",
                                files={"file": (path.name, data)})
                ok = r.status_code == 201
                check(f"ingest {path.name}", ok,
                      f"chunks={r.json().get('chunk_count') if ok else r.text}")

            print("· queries (grounded + cited)")
            for question, expected_source in QUESTIONS:
                r = client.post("/v1/query", json={
                    "question": question, "namespace": "demo", "include_chunks": True,
                })
                body = r.json()
                sources = {c["filename"] for c in body.get("citations", [])}
                check(f"Q: {question[:48]}",
                      r.status_code == 200 and body.get("grounded") is True,
                      f"cited={sorted(sources)}")

            print("· admin & dashboard")
            stats = client.get("/v1/admin/stats").json()
            check("stats documents", stats["total_documents"] >= 3,
                  f"docs={stats['total_documents']} chunks={stats['total_chunks']}")
            metrics = client.get("/v1/admin/metrics").json()
            check("metrics recorded", metrics["total_queries"] >= len(QUESTIONS))
            check("dashboard serves", client.get("/dashboard").status_code == 200)
            check("dashboard assets", client.get("/dashboard/static/app.js").status_code == 200)

    print()
    if failures:
        print(f"SMOKE TEST FAILED — {len(failures)} check(s) failed: {failures}")
        return 1
    print("SMOKE TEST PASSED — all checks green ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
