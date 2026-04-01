import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_ALIPAY = ROOT / "账单" / "支付宝交易明细(20260228-20260331).csv"
SAMPLE_WECHAT = (
    ROOT / "账单" / "微信支付账单流水文件(20260301-20260331)_20260331164906.xlsx"
)


def _login(client: TestClient, username: str, password: str) -> None:
    r = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEDGER_BOOTSTRAP_ADMIN_USER", "adm")
    monkeypatch.setenv("LEDGER_BOOTSTRAP_ADMIN_PASSWORD", "admin1")

    import app.main as main

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    p = Path(path)
    monkeypatch.setattr(main, "DB_PATH", p)
    main.init_db()
    with TestClient(main.app) as c:
        yield c, main
    p.unlink(missing_ok=True)


def test_health_no_auth(client):
    c, _ = client
    r = c.get("/api/health")
    assert r.status_code == 200


def test_summary_requires_login(client):
    c, _ = client
    r = c.get("/api/summary")
    assert r.status_code == 401


def test_create_and_summary_as_user(client):
    c, _ = client
    _login(c, "adm", "admin1")
    c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 12.5, "note": "午餐"},
    )
    c.post(
        "/api/transactions",
        json={"type": "income", "amount": 100, "note": "工资"},
    )
    r = c.get("/api/summary")
    assert r.json() == {
        "total_expense": 12.5,
        "total_income": 100.0,
        "net": 87.5,
        "overall_expense": 12.5,
        "overall_income": 100.0,
        "overall_net": 87.5,
        "has_filter": False,
    }


def test_two_users_isolated(client):
    c, main = client
    _login(c, "adm", "admin1")
    r = c.post(
        "/api/admin/users",
        json={"username": "usr2", "password": "user2pw", "role": "user"},
    )
    assert r.status_code == 200, r.text

    c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 50, "note": "admin-spend"},
    )

    c2 = TestClient(main.app)
    _login(c2, "usr2", "user2pw")
    c2.post(
        "/api/transactions",
        json={"type": "income", "amount": 10, "note": "u2-only"},
    )

    sum_a = c.get("/api/summary").json()
    sum_b = c2.get("/api/summary").json()
    assert sum_a["total_expense"] == 50.0
    assert sum_a["total_income"] == 0.0
    assert sum_b["total_expense"] == 0.0
    assert sum_b["total_income"] == 10.0

    list_b = c2.get("/api/transactions").json()
    assert len(list_b) == 1
    assert list_b[0]["note"] == "u2-only"


def test_user_cannot_admin(client):
    c, _ = client
    _login(c, "adm", "admin1")
    c.post(
        "/api/admin/users",
        json={"username": "usr3", "password": "user3pw", "role": "user"},
    )
    c.post("/api/auth/logout", json={})
    _login(c, "usr3", "user3pw")
    r = c.get("/api/admin/users")
    assert r.status_code == 403


def test_patch_transaction(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 1, "note": "a"},
    )
    tid = r.json()["id"]
    r2 = c.patch(f"/api/transactions/{tid}", json={"note": "b"})
    assert r2.status_code == 200
    assert r2.json()["note"] == "b"


def test_patch_requires_field(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.post(
        "/api/transactions",
        json={"type": "income", "amount": 5, "note": ""},
    )
    tid = r.json()["id"]
    r2 = c.patch(f"/api/transactions/{tid}", json={})
    assert r2.status_code == 422


def test_transacted_on_default_and_filter(client):
    c, _ = client
    _login(c, "adm", "admin1")
    c.post("/api/transactions", json={"type": "expense", "amount": 10, "note": "a"})
    c.post(
        "/api/transactions",
        json={"type": "income", "amount": 20, "note": "b", "transacted_on": "2024-12-31"},
    )
    all_rows = c.get("/api/transactions").json()
    assert len(all_rows) == 2
    assert all_rows[0]["transacted_on"]
    only_2024 = c.get("/api/transactions?year=2024").json()
    assert len(only_2024) == 1
    assert only_2024[0]["transacted_on"] == "2024-12-31"


def test_summary_with_filter_and_overall(client):
    c, _ = client
    _login(c, "adm", "admin1")
    c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 30, "note": "m1", "transacted_on": "2025-01-01"},
    )
    c.post(
        "/api/transactions",
        json={"type": "income", "amount": 100, "note": "m2", "transacted_on": "2025-02-01"},
    )
    r = c.get("/api/summary?year=2025&month=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total_expense"] == 0.0
    assert body["total_income"] == 100.0
    assert body["net"] == 100.0
    assert body["overall_expense"] == 30.0
    assert body["overall_income"] == 100.0
    assert body["overall_net"] == 70.0
    assert body["has_filter"] is True


def test_month_requires_year(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.get("/api/summary?month=3")
    assert r.status_code == 400


def test_date_range_filter(client):
    c, _ = client
    _login(c, "adm", "admin1")
    c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 10, "note": "a", "transacted_on": "2026-01-10"},
    )
    c.post(
        "/api/transactions",
        json={"type": "income", "amount": 20, "note": "b", "transacted_on": "2026-03-10"},
    )
    r = c.get("/api/summary?start_date=2026-03-01&end_date=2026-03-31")
    assert r.status_code == 200
    body = r.json()
    assert body["total_expense"] == 0.0
    assert body["total_income"] == 20.0
    assert body["has_filter"] is True


def test_date_range_requires_pair(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.get("/api/summary?start_date=2026-03-01")
    assert r.status_code == 400


def test_grouped_endpoint(client):
    c, _ = client
    _login(c, "adm", "admin1")
    c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 10, "note": "g1", "transacted_on": "2026-03-01"},
    )
    c.post(
        "/api/transactions",
        json={"type": "income", "amount": 40, "note": "g2", "transacted_on": "2026-03-02"},
    )
    c.post(
        "/api/transactions",
        json={"type": "income", "amount": 5, "note": "g3", "transacted_on": "2026-02-01"},
    )
    r = c.get("/api/transactions/grouped?year=2026")
    assert r.status_code == 200
    body = r.json()
    assert body["total_groups"] == 2
    assert body["total_records"] == 3
    assert body["groups"][0]["year"] == 2026


@pytest.mark.skipif(not SAMPLE_ALIPAY.is_file(), reason="无支付宝样例文件")
def test_import_alipay_sample(client):
    c, _ = client
    _login(c, "adm", "admin1")
    raw = SAMPLE_ALIPAY.read_bytes()
    r = c.post(
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("明细.csv", raw, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] > 0
    assert body["skipped_duplicate"] == 0
    rows = c.get("/api/transactions").json()
    imported = [x for x in rows if x.get("import_platform") == "alipay"]
    assert len(imported) == body["inserted"]
    one = max(imported, key=lambda x: x["amount"])
    assert one.get("bill_counterparty")


def test_import_requires_login(client):
    c, _ = client
    r = c.post(
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("x.csv", "交易时间\n".encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 401


def test_import_wrong_extension(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.post(
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("x.txt", b"a", "text/plain")},
    )
    assert r.status_code == 400


@pytest.mark.skipif(not SAMPLE_ALIPAY.is_file(), reason="无支付宝样例文件")
def test_import_idempotent_alipay(client):
    c, _ = client
    _login(c, "adm", "admin1")
    raw = SAMPLE_ALIPAY.read_bytes()
    r1 = c.post(
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("明细.csv", io.BytesIO(raw), "text/csv")},
    )
    assert r1.status_code == 200
    n0 = r1.json()["inserted"]
    assert n0 > 0
    r2 = c.post(
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("明细.csv", io.BytesIO(raw), "text/csv")},
    )
    assert r2.status_code == 200
    assert r2.json()["inserted"] == 0
    assert r2.json()["skipped_duplicate"] == n0


@pytest.mark.skipif(not SAMPLE_WECHAT.is_file(), reason="无微信样例文件")
def test_import_wechat_sample(client):
    c, _ = client
    _login(c, "adm", "admin1")
    raw = SAMPLE_WECHAT.read_bytes()
    r = c.post(
        "/api/transactions/import",
        data={"platform": "wechat"},
        files={"file": ("账单.xlsx", raw, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] > 0
