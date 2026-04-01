import io
import os
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_ALIPAY = ROOT / "账单" / "支付宝交易明细(20260228-20260331).csv"
SAMPLE_WECHAT = (
    ROOT / "账单" / "微信支付账单流水文件(20260301-20260331)_20260331164906.xlsx"
)

CSRF_COOKIE = "ledger_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _csrf_headers(c: TestClient) -> dict[str, str]:
    if CSRF_COOKIE not in c.cookies:
        r = c.get("/api/health")
        assert r.status_code == 200, r.text
    return {CSRF_HEADER: c.cookies[CSRF_COOKIE]}


def _post(c: TestClient, url: str, **kwargs):
    headers = {**_csrf_headers(c), **(kwargs.pop("headers", None) or {})}
    return c.post(url, headers=headers, **kwargs)


def _patch(c: TestClient, url: str, **kwargs):
    headers = {**_csrf_headers(c), **(kwargs.pop("headers", None) or {})}
    return c.patch(url, headers=headers, **kwargs)


def _delete(c: TestClient, url: str, **kwargs):
    headers = {**_csrf_headers(c), **(kwargs.pop("headers", None) or {})}
    return c.delete(url, headers=headers, **kwargs)


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

    main._login_fail_buckets.clear()
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
    assert "content-security-policy" in {k.lower() for k in r.headers}
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_summary_requires_login(client):
    c, _ = client
    r = c.get("/api/summary")
    assert r.status_code == 401


def test_create_and_summary_as_user(client):
    c, _ = client
    _login(c, "adm", "admin1")
    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 12.5, "note": "午餐"},
    )
    _post(
        c,
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
    r = _post(
        c,
        "/api/admin/users",
        json={"username": "usr2", "password": "user2pw", "role": "user"},
    )
    assert r.status_code == 200, r.text

    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 50, "note": "admin-spend"},
    )

    c2 = TestClient(main.app)
    _login(c2, "usr2", "user2pw")
    _post(
        c2,
        "/api/transactions",
        json={"type": "income", "amount": 10, "note": "u2-only"},
    )

    sum_a = c.get("/api/summary").json()
    sum_b = c2.get("/api/summary").json()
    assert sum_a["total_expense"] == 50.0
    assert sum_a["total_income"] == 0.0
    assert sum_b["total_expense"] == 0.0
    assert sum_b["total_income"] == 10.0

    list_b = c2.get("/api/transactions").json()["items"]
    assert len(list_b) == 1
    assert list_b[0]["note"] == "u2-only"


def test_user_cannot_admin(client):
    c, _ = client
    _login(c, "adm", "admin1")
    _post(
        c,
        "/api/admin/users",
        json={"username": "usr3", "password": "user3pw", "role": "user"},
    )
    _post(c, "/api/auth/logout", json={})
    _login(c, "usr3", "user3pw")
    r = c.get("/api/admin/users")
    assert r.status_code == 403


def test_patch_transaction(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 1, "note": "a"},
    )
    tid = r.json()["id"]
    r2 = _patch(c, f"/api/transactions/{tid}", json={"note": "b"})
    assert r2.status_code == 200
    assert r2.json()["note"] == "b"


def test_patch_requires_field(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = _post(
        c,
        "/api/transactions",
        json={"type": "income", "amount": 5, "note": ""},
    )
    tid = r.json()["id"]
    r2 = _patch(c, f"/api/transactions/{tid}", json={})
    assert r2.status_code == 422


def test_transacted_on_default_and_filter(client):
    c, _ = client
    _login(c, "adm", "admin1")
    _post(c, "/api/transactions", json={"type": "expense", "amount": 10, "note": "a"})
    _post(
        c,
        "/api/transactions",
        json={"type": "income", "amount": 20, "note": "b", "transacted_on": "2024-12-31"},
    )
    all_rows = c.get("/api/transactions").json()["items"]
    assert len(all_rows) == 2
    assert all_rows[0]["transacted_on"]
    only_2024 = c.get("/api/transactions?year=2024").json()["items"]
    assert len(only_2024) == 1
    assert only_2024[0]["transacted_on"] == "2024-12-31"


def test_summary_with_filter_and_overall(client):
    c, _ = client
    _login(c, "adm", "admin1")
    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 30, "note": "m1", "transacted_on": "2025-01-01"},
    )
    _post(
        c,
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
    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 10, "note": "a", "transacted_on": "2026-01-10"},
    )
    _post(
        c,
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
    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 10, "note": "g1", "transacted_on": "2026-03-01"},
    )
    _post(
        c,
        "/api/transactions",
        json={"type": "income", "amount": 40, "note": "g2", "transacted_on": "2026-03-02"},
    )
    _post(
        c,
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
    r = _post(
        c,
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("明细.csv", raw, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] > 0
    assert body["skipped_duplicate"] == 0
    rows: list = []
    page = 1
    while True:
        part = c.get(f"/api/transactions?page={page}&page_size=200").json()
        rows.extend(part["items"])
        if len(rows) >= part["total"]:
            break
        page += 1
    imported = [x for x in rows if x.get("import_platform") == "alipay"]
    assert len(imported) == body["inserted"]
    one = max(imported, key=lambda x: x["amount"])
    assert one.get("bill_counterparty")


def test_import_requires_login(client):
    c, _ = client
    c.get("/api/health")
    r = _post(
        c,
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("x.csv", "交易时间\n".encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 401


def test_import_wrong_extension(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = _post(
        c,
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
    r1 = _post(
        c,
        "/api/transactions/import",
        data={"platform": "alipay"},
        files={"file": ("明细.csv", io.BytesIO(raw), "text/csv")},
    )
    assert r1.status_code == 200
    n0 = r1.json()["inserted"]
    assert n0 > 0
    r2 = _post(
        c,
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
    r = _post(
        c,
        "/api/transactions/import",
        data={"platform": "wechat"},
        files={"file": ("账单.xlsx", raw, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] > 0


def test_csrf_rejects_missing_header(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.post(
        "/api/transactions",
        json={"type": "expense", "amount": 1, "note": "x"},
    )
    assert r.status_code == 403
    assert "CSRF" in r.json().get("detail", "")


def test_login_rate_limit_then_recovery(client, monkeypatch):
    c, main = client
    main._login_fail_buckets.clear()
    t0 = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: t0)
    for _ in range(5):
        r = c.post("/api/auth/login", json={"username": "adm", "password": "bad"})
        assert r.status_code == 401
    r6 = c.post("/api/auth/login", json={"username": "adm", "password": "bad"})
    assert r6.status_code == 429
    t0 += main.LOGIN_RATE_WINDOW_SEC + 1
    rok = c.post("/api/auth/login", json={"username": "adm", "password": "admin1"})
    assert rok.status_code == 200


def test_password_special_chars_create_and_login(client):
    c, main = client
    _login(c, "adm", "admin1")
    pw = "aZ9!#$%^&*()-_+=~"
    r = _post(
        c,
        "/api/admin/users",
        json={"username": "speuser", "password": pw, "role": "user"},
    )
    assert r.status_code == 200, r.text
    c2 = TestClient(main.app)
    _login(c2, "speuser", pw)
    assert c2.get("/api/me").status_code == 200


def test_expired_sessions_removed_on_init(client):
    c, main = client
    _login(c, "adm", "admin1")
    tok = c.cookies.get("ledger_session")
    assert tok
    with main.get_conn() as conn:
        conn.execute("UPDATE sessions SET expires_at = 1 WHERE token = ?", (tok,))
    main.init_db()
    r = c.get("/api/me")
    assert r.status_code == 401


def test_session_delete_endpoint(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 3, "note": "delme"},
    )
    tid = r.json()["id"]
    rd = _delete(c, f"/api/transactions/{tid}")
    assert rd.status_code == 200


def test_https_forwarded_proto_sets_secure_cookie(client):
    c, _ = client
    r = c.post(
        "/api/auth/login",
        json={"username": "adm", "password": "admin1"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert r.status_code == 200
    set_cookie = r.headers.get("set-cookie", "")
    assert "Secure" in set_cookie


def test_transactions_pagination(client):
    c, _ = client
    _login(c, "adm", "admin1")
    for i in range(3):
        _post(
            c,
            "/api/transactions",
            json={"type": "expense", "amount": 1, "note": f"n{i}"},
        )
    r = c.get("/api/transactions?page=1&page_size=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
    r2 = c.get("/api/transactions?page=2&page_size=2")
    assert len(r2.json()["items"]) == 1


def test_transactions_keyword_search(client):
    c, _ = client
    _login(c, "adm", "admin1")
    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 1, "note": "hello world"},
    )
    _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 2, "note": "other"},
    )
    r = c.get("/api/transactions?keyword=hello")
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["note"] == "hello world"


def test_keyword_on_bill_field(client):
    c, main = client
    _login(c, "adm", "admin1")
    uid = c.get("/api/me").json()["id"]
    ts = "2026-04-01T00:00:00Z"
    with main.get_conn() as conn:
        conn.execute(
            """
            INSERT INTO transactions (
                user_id, type, amount_cents, note, transacted_on,
                created_at, updated_at, bill_counterparty
            ) VALUES (?, 'expense', 100, '', '2026-04-01', ?, ?, '咖啡店')
            """,
            (uid, ts, ts),
        )
    r = c.get("/api/transactions?keyword=咖啡")
    assert r.json()["total"] == 1


def test_export_csv(client):
    c, _ = client
    _login(c, "adm", "admin1")
    _post(
        c,
        "/api/transactions",
        json={"type": "income", "amount": 3, "note": "导出测"},
    )
    r = c.get("/api/transactions/export")
    assert r.status_code == 200
    assert "csv" in r.headers.get("content-type", "").lower()
    text = r.content.decode("utf-8-sig")
    assert "收入" in text or "income" in text.lower()
    assert "导出测" in text


def test_export_empty_csv_headers(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = c.get("/api/transactions/export")
    assert r.status_code == 200
    text = r.content.decode("utf-8-sig")
    assert "类型" in text
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    assert len(lines) == 1


def test_patch_type_and_transacted_on(client):
    c, _ = client
    _login(c, "adm", "admin1")
    r = _post(
        c,
        "/api/transactions",
        json={"type": "expense", "amount": 5, "note": "n"},
    )
    tid = r.json()["id"]
    r2 = _patch(
        c,
        f"/api/transactions/{tid}",
        json={
            "type": "income",
            "transacted_on": "2020-06-15",
            "amount": 5,
            "note": "n2",
        },
    )
    assert r2.status_code == 200
    j = r2.json()
    assert j["type"] == "income"
    assert j["transacted_on"] == "2020-06-15"
    assert j["note"] == "n2"


def test_me_password(client):
    c, main = client
    _login(c, "adm", "admin1")
    bad = _post(
        c,
        "/api/me/password",
        json={"old_password": "wrong", "new_password": "newpw99"},
    )
    assert bad.status_code == 400
    ok = _post(
        c,
        "/api/me/password",
        json={"old_password": "admin1", "new_password": "newpw99"},
    )
    assert ok.status_code == 200
    c2 = TestClient(main.app)
    fail = c2.post(
        "/api/auth/login",
        json={"username": "adm", "password": "admin1"},
    )
    assert fail.status_code == 401
    good = c2.post(
        "/api/auth/login",
        json={"username": "adm", "password": "newpw99"},
    )
    assert good.status_code == 200


def test_admin_delete_user_and_data(client):
    c, main = client
    _login(c, "adm", "admin1")
    r = _post(
        c,
        "/api/admin/users",
        json={"username": "gone", "password": "gonepw9", "role": "user"},
    )
    uid = r.json()["id"]
    c2 = TestClient(main.app)
    _login(c2, "gone", "gonepw9")
    _post(c2, "/api/transactions", json={"type": "expense", "amount": 1, "note": "x"})
    _post(c2, "/api/auth/logout", json={})
    _login(c, "adm", "admin1")
    rd = _delete(c, f"/api/admin/users/{uid}")
    assert rd.status_code == 200
    c3 = TestClient(main.app)
    login_gone = c3.post(
        "/api/auth/login",
        json={"username": "gone", "password": "gonepw9"},
    )
    assert login_gone.status_code == 401


def test_admin_cannot_delete_self(client):
    c, _ = client
    _login(c, "adm", "admin1")
    me = c.get("/api/me").json()
    rd = _delete(c, f"/api/admin/users/{me['id']}")
    assert rd.status_code == 400


def test_wal_enabled(client):
    _, main = client
    with main.get_conn() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"
