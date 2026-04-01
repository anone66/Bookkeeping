"""个人收支记账：多用户 + 管理端；FastAPI + SQLite。"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import secrets
import sqlite3
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app import bill_import

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "ledger.db"
STATIC_DIR = ROOT / "static"

SESSION_COOKIE = "ledger_session"
SESSION_DAYS = 7
COOKIE_PATH = "/"
COOKIE_SAMESITE = "lax"
CSRF_COOKIE = "ledger_csrf"
CSRF_HEADER = "X-CSRF-Token"
COOKIE_KWARGS = {"httponly": True, "samesite": COOKIE_SAMESITE, "path": COOKIE_PATH}

USERNAME_RE = re.compile(r"^[a-zA-Z0-9@.]{3,64}$")
# 字母、数字、@ . 及常用特殊字符（与前端 pattern 同步）
PASSWORD_RE = re.compile(r"^[a-zA-Z0-9@.!#$%^&*()\-_+=~]{6,128}$")

LOGIN_RATE_WINDOW_SEC = 60.0
LOGIN_RATE_MAX_FAILURES = 5
_login_fail_buckets: dict[str, list[float]] = {}
_lazy_session_clean_counter = 0
LAZY_SESSION_CLEAN_EVERY = 50

SECURITY_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "form-action 'self'"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _exp_ts() -> int:
    return int(time.time()) + SESSION_DAYS * 86400


def to_cents(amount: float) -> int:
    c = round(float(amount) * 100)
    if c <= 0:
        raise ValueError("金额必须大于 0")
    return c


def from_cents(cents: int) -> float:
    return round(cents / 100.0, 2)


def validate_username(username: str) -> str:
    u = username.strip().lower()
    if not USERNAME_RE.fullmatch(u):
        raise ValueError("用户名须为 3–64 位，仅字母、数字、@、.")
    return u


def validate_password(password: str) -> None:
    if not PASSWORD_RE.fullmatch(password):
        raise ValueError(
            "密码须至少 6 位，可为字母、数字、@ . 及 ! # $ % ^ & * ( ) - _ + = ~ 等常用符号"
        )


def _request_is_secure(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    forwarded = (request.headers.get("x-forwarded-proto") or "").strip().lower()
    return forwarded.split(",")[0].strip() == "https"


def _session_cookie_kwargs(request: Request) -> dict:
    return {
        **COOKIE_KWARGS,
        "secure": _request_is_secure(request),
    }


def _csrf_cookie_kwargs(request: Request) -> dict:
    return {
        "httponly": False,
        "samesite": COOKIE_SAMESITE,
        "path": COOKIE_PATH,
        "secure": _request_is_secure(request),
    }


def _csrf_tokens_match(cookie_val: str | None, header_val: str | None) -> bool:
    if not cookie_val or not header_val:
        return False
    if len(cookie_val) != len(header_val):
        return False
    return secrets.compare_digest(cookie_val, header_val)


def _csrf_check_required(path: str, method: str) -> bool:
    if method not in ("POST", "PATCH", "DELETE"):
        return False
    if not path.startswith("/api/"):
        return False
    if path == "/api/auth/login":
        return False
    return True


def _client_rate_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _login_failures_in_window(request: Request) -> list[float]:
    key = _client_rate_key(request)
    now = time.time()
    bucket = _login_fail_buckets.setdefault(key, [])
    cutoff = now - LOGIN_RATE_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    return bucket


def _login_rate_precheck(request: Request) -> None:
    if len(_login_failures_in_window(request)) >= LOGIN_RATE_MAX_FAILURES:
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")


def _login_rate_record_failure(request: Request) -> None:
    bucket = _login_failures_in_window(request)
    bucket.append(time.time())


def _login_rate_clear(request: Request) -> None:
    _login_fail_buckets.pop(_client_rate_key(request), None)


def _attach_security_headers(response: Response) -> None:
    response.headers.setdefault("Content-Security-Policy", SECURITY_CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")


def delete_expired_sessions(conn: sqlite3.Connection, now_ts: int | None = None) -> None:
    ts = int(time.time()) if now_ts is None else now_ts
    conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (ts,))


def check_username(username: str) -> str:
    try:
        return validate_username(username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def check_password(password: str) -> None:
    try:
        validate_password(password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("ascii")
        )
    except ValueError:
        return False


@contextmanager
def get_conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def bootstrap_if_no_users(conn: sqlite3.Connection) -> None:
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if n > 0:
        return
    u = os.environ.get("LEDGER_BOOTSTRAP_ADMIN_USER", "").strip().lower()
    p = os.environ.get("LEDGER_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not u or not p:
        logger.error(
            "数据库中尚无用户，且未设置环境变量 LEDGER_BOOTSTRAP_ADMIN_USER / "
            "LEDGER_BOOTSTRAP_ADMIN_PASSWORD，拒绝启动。"
        )
        sys.exit(1)
    try:
        validate_username(u)
        validate_password(p)
    except ValueError as e:
        logger.error("首轮管理员环境变量无效：%s", e)
        sys.exit(1)
    h = hash_password(p)
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at)
        VALUES (?, ?, 'admin', 1, ?, ?)
        """,
        (u, h, now, now),
    )
    logger.info("已根据环境变量创建首轮管理员：%s", u)


def migrate_transactions(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='transactions'"
    ).fetchone()
    if not exists:
        conn.executescript(
            """
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                note TEXT NOT NULL DEFAULT '',
                transacted_on TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                import_platform TEXT,
                external_id TEXT,
                bill_category TEXT,
                bill_counterparty TEXT,
                bill_product TEXT,
                bill_payment_method TEXT,
                bill_merchant_no TEXT,
                bill_export_note TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tx_user_created
                ON transactions (user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tx_user_transacted
                ON transactions (user_id, transacted_on DESC, id DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_user_import_dedupe
                ON transactions (user_id, import_platform, external_id)
                WHERE import_platform IS NOT NULL
                  AND external_id IS NOT NULL
                  AND TRIM(external_id) != '';
            """
        )
        return
    cols = _table_columns(conn, "transactions")
    if "user_id" not in cols:
        uid = conn.execute(
            "SELECT id FROM users ORDER BY id LIMIT 1"
        ).fetchone()
        if not uid:
            raise RuntimeError("迁移 transactions 需要至少一名用户")
        uid = uid[0]
        conn.execute("ALTER TABLE transactions ADD COLUMN user_id INTEGER")
        conn.execute(
            "UPDATE transactions SET user_id = ? WHERE user_id IS NULL", (uid,)
        )
    cols = _table_columns(conn, "transactions")
    if "transacted_on" not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN transacted_on TEXT")
    conn.execute(
        """
        UPDATE transactions
        SET transacted_on = SUBSTR(created_at, 1, 10)
        WHERE transacted_on IS NULL OR TRIM(transacted_on) = ''
        """
    )
    _TX_IMPORT_COLS: tuple[tuple[str, str], ...] = (
        ("import_platform", "TEXT"),
        ("external_id", "TEXT"),
        ("bill_category", "TEXT"),
        ("bill_counterparty", "TEXT"),
        ("bill_product", "TEXT"),
        ("bill_payment_method", "TEXT"),
        ("bill_merchant_no", "TEXT"),
        ("bill_export_note", "TEXT"),
    )
    cols = _table_columns(conn, "transactions")
    for col_name, col_sql in _TX_IMPORT_COLS:
        if col_name not in cols:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_sql}")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_user_import_dedupe
            ON transactions (user_id, import_platform, external_id)
            WHERE import_platform IS NOT NULL
              AND external_id IS NOT NULL
              AND TRIM(external_id) != ''
        """
    )


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions (expires_at);
            """
        )
        bootstrap_if_no_users(conn)
        migrate_transactions(conn)
        delete_expired_sessions(conn)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tx_user_created
                ON transactions (user_id, created_at DESC)
            """
        )
        conn.execute("DROP INDEX IF EXISTS idx_transactions_created_at")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tx_user_transacted
                ON transactions (user_id, transacted_on DESC, id DESC)
            """
        )
        conn.execute(
            """
            UPDATE transactions
            SET transacted_on = SUBSTR(created_at, 1, 10)
            WHERE transacted_on IS NULL OR TRIM(transacted_on) = ''
            """
        )


def row_to_tx(r: sqlite3.Row) -> dict:
    d: dict = {
        "id": r["id"],
        "type": r["type"],
        "amount": from_cents(r["amount_cents"]),
        "note": r["note"] or "",
        "transacted_on": r["transacted_on"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
    for k in (
        "import_platform",
        "external_id",
        "bill_category",
        "bill_counterparty",
        "bill_product",
        "bill_payment_method",
        "bill_merchant_no",
        "bill_export_note",
    ):
        if k not in r.keys():
            continue
        v = r[k]
        if v is None or (isinstance(v, str) and v == ""):
            d[k] = None
        else:
            d[k] = v
    return d


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str


class LoginBody(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    id: int
    username: str
    role: str


class MePasswordBody(BaseModel):
    old_password: str
    new_password: str


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = Field(default="user", pattern="^(admin|user)$")


class AdminUserPatch(BaseModel):
    is_active: bool | None = None
    password: str | None = None

    @model_validator(mode="after")
    def one_field(self):
        if self.is_active is None and self.password is None:
            raise ValueError("至少需要修改启用状态或密码之一")
        return self


class TransactionCreate(BaseModel):
    type: str = Field(pattern="^(expense|income)$")
    amount: float = Field(gt=0, description="元，正数")
    note: str = ""
    transacted_on: str | None = Field(
        default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="交易发生日期 YYYY-MM-DD"
    )


class TransactionPatch(BaseModel):
    note: str | None = None
    amount: float | None = Field(default=None, gt=0, description="元，正数；不传则不修改")
    type: str | None = Field(default=None, pattern="^(expense|income)$")
    transacted_on: str | None = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="交易发生日期 YYYY-MM-DD",
    )

    @model_validator(mode="after")
    def at_least_one_field(self):
        if (
            self.note is None
            and self.amount is None
            and self.type is None
            and self.transacted_on is None
        ):
            raise ValueError("至少需要修改说明、金额、类型或交易日期之一")
        return self


class SummaryOut(BaseModel):
    total_expense: float
    total_income: float
    net: float
    overall_expense: float
    overall_income: float
    overall_net: float
    has_filter: bool


class GroupSummaryOut(BaseModel):
    year: int
    month: int
    total_expense: float
    total_income: float
    net: float
    count: int


def _period_clause(
    year: int | None,
    month: int | None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[str, tuple[str, ...], bool]:
    if start_date is not None or end_date is not None:
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date 与 end_date 需同时提供")
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            raise HTTPException(status_code=400, detail="日期格式需为 YYYY-MM-DD") from e
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")
        return " AND transacted_on >= ? AND transacted_on <= ?", (start_date, end_date), True

    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="仅指定 month 时必须同时指定 year")
    if year is not None and not (1900 <= year <= 2999):
        raise HTTPException(status_code=400, detail="year 超出允许范围")
    if month is not None and not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="month 必须在 1 到 12 之间")

    if year is None:
        return "", tuple(), False
    if month is None:
        return " AND SUBSTR(transacted_on, 1, 4) = ?", (f"{year:04d}",), True
    return (
        " AND SUBSTR(transacted_on, 1, 7) = ?",
        (f"{year:04d}-{month:02d}",),
        True,
    )


def _keyword_clause(keyword: str | None) -> tuple[str, tuple[str, ...]]:
    if keyword is None:
        return "", ()
    k = keyword.strip()
    if not k:
        return "", ()
    esc = k.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pat = f"%{esc}%"
    clause = (
        " AND (note LIKE ? ESCAPE '\\' OR IFNULL(bill_counterparty,'') LIKE ? ESCAPE '\\' "
        "OR IFNULL(bill_product,'') LIKE ? ESCAPE '\\')"
    )
    return clause, (pat, pat, pat)


def _tx_where_suffix(
    year: int | None,
    month: int | None,
    start_date: str | None,
    end_date: str | None,
    keyword: str | None,
) -> tuple[str, tuple[str, ...]]:
    where_sql, where_params, _ = _period_clause(year, month, start_date, end_date)
    kw_sql, kw_params = _keyword_clause(keyword)
    return where_sql + kw_sql, where_params + kw_params


def get_current_user(request: Request) -> CurrentUser:
    global _lazy_session_clean_counter
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    now_ts = int(time.time())
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.role, u.is_active
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, now_ts),
        ).fetchone()
        if row and row["is_active"]:
            _lazy_session_clean_counter += 1
            if _lazy_session_clean_counter % LAZY_SESSION_CLEAN_EVERY == 0:
                delete_expired_sessions(conn, now_ts)
            return CurrentUser(
                id=row["id"], username=row["username"], role=row["role"]
            )
        if row:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    raise HTTPException(status_code=401, detail="未登录或已禁用")


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, _exp_ts()),
    )
    return token


def revoke_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Personal Ledger", version="0.2.0", lifespan=lifespan)


@app.middleware("http")
async def security_and_csrf_middleware(request: Request, call_next):
    if _csrf_check_required(request.url.path, request.method):
        if not _csrf_tokens_match(
            request.cookies.get(CSRF_COOKIE),
            request.headers.get(CSRF_HEADER),
        ):
            resp = JSONResponse({"detail": "CSRF 校验失败"}, status_code=403)
            _attach_security_headers(resp)
            if CSRF_COOKIE not in request.cookies:
                resp.set_cookie(
                    CSRF_COOKIE,
                    secrets.token_urlsafe(32),
                    max_age=SESSION_DAYS * 86400,
                    **_csrf_cookie_kwargs(request),
                )
            return resp
    response = await call_next(request)
    _attach_security_headers(response)
    if CSRF_COOKIE not in request.cookies:
        response.set_cookie(
            CSRF_COOKIE,
            secrets.token_urlsafe(32),
            max_age=SESSION_DAYS * 86400,
            **_csrf_cookie_kwargs(request),
        )
    return response


@app.post("/api/auth/login")
def api_login(request: Request, body: LoginBody, response: Response):
    _login_rate_precheck(request)
    username = check_username(body.username)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row or not row["is_active"]:
            _login_rate_record_failure(request)
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        if not verify_password(body.password, row["password_hash"]):
            _login_rate_record_failure(request)
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        token = create_session(conn, row["id"])
    _login_rate_clear(request)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        **_session_cookie_kwargs(request),
    )
    return {"ok": True}


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    with get_conn() as conn:
        revoke_session(conn, token)
    sk = _session_cookie_kwargs(request)
    response.delete_cookie(
        SESSION_COOKIE,
        path=COOKIE_PATH,
        httponly=True,
        samesite=COOKIE_SAMESITE,
        secure=sk["secure"],
    )
    return {"ok": True}


@app.get("/api/me", response_model=MeOut)
def api_me(user: CurrentUser = Depends(get_current_user)):
    return MeOut(id=user.id, username=user.username, role=user.role)


@app.post("/api/me/password")
def api_me_password(body: MePasswordBody, user: CurrentUser = Depends(get_current_user)):
    check_password(body.new_password)
    now = _now_iso()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user.id,)
        ).fetchone()
        if not row or not verify_password(body.old_password, row["password_hash"]):
            raise HTTPException(status_code=400, detail="旧密码不正确")
        conn.execute(
            """
            UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?
            """,
            (hash_password(body.new_password), now, user.id),
        )
    return {"ok": True}


@app.get("/api/admin/users")
def api_admin_users(_admin: CurrentUser = Depends(require_admin)):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, is_active, created_at
            FROM users ORDER BY id
            """
        ).fetchall()
    return [
        {
            "id": r["id"],
            "username": r["username"],
            "role": r["role"],
            "is_active": bool(r["is_active"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@app.post("/api/admin/users")
def api_admin_create(body: AdminUserCreate, _admin: CurrentUser = Depends(require_admin)):
    username = check_username(body.username)
    check_password(body.password)
    now = _now_iso()
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (username, hash_password(body.password), body.role, now, now),
            )
            uid = cur.lastrowid
            row = conn.execute(
                """
                SELECT id, username, role, is_active, created_at FROM users WHERE id = ?
                """,
                (uid,),
            ).fetchone()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail="用户名已存在") from e
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


@app.patch("/api/admin/users/{user_id}")
def api_admin_patch(
    user_id: int, body: AdminUserPatch, admin: CurrentUser = Depends(require_admin)
):
    if user_id == admin.id and body.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前登录的管理员")
    if body.password is not None:
        check_password(body.password)
    now = _now_iso()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        if body.is_active is not None:
            if body.is_active:
                conn.execute(
                    "UPDATE users SET is_active = 1, updated_at = ? WHERE id = ?",
                    (now, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET is_active = 0, updated_at = ? WHERE id = ?",
                    (now, user_id),
                )
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        if body.password is not None:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(body.password), now, user_id),
            )
        row = conn.execute(
            """
            SELECT id, username, role, is_active, created_at
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


@app.delete("/api/admin/users/{user_id}")
def api_admin_delete(user_id: int, admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员")
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"ok": True}


@app.get("/api/summary", response_model=SummaryOut)
def api_summary(
    year: int | None = None,
    month: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    where_sql, where_params, has_filter = _period_clause(
        year, month, start_date, end_date
    )
    with get_conn() as conn:
        overall = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents END), 0) AS exp_c,
              COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents END), 0) AS inc_c
            FROM transactions
            WHERE user_id = ?
            """,
            (user.id,),
        ).fetchone()
        if where_sql:
            row = conn.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents END), 0) AS exp_c,
                  COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents END), 0) AS inc_c
                FROM transactions
                WHERE user_id = ?
                """
                + where_sql,
                (user.id, *where_params),
            ).fetchone()
        else:
            row = overall
    exp_c, inc_c = int(row["exp_c"]), int(row["inc_c"])
    o_exp_c, o_inc_c = int(overall["exp_c"]), int(overall["inc_c"])
    te, ti = from_cents(exp_c), from_cents(inc_c)
    ote, oti = from_cents(o_exp_c), from_cents(o_inc_c)
    return SummaryOut(
        total_expense=te,
        total_income=ti,
        net=ti - te,
        overall_expense=ote,
        overall_income=oti,
        overall_net=oti - ote,
        has_filter=has_filter,
    )


@app.get("/api/transactions/grouped")
def api_grouped(
    year: int | None = None,
    month: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    where_sql, where_params, _ = _period_clause(year, month, start_date, end_date)
    with get_conn() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM transactions WHERE user_id = ?" + where_sql,
            (user.id, *where_params),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT
                SUBSTR(transacted_on, 1, 4) AS y,
                SUBSTR(transacted_on, 6, 2) AS m,
                COUNT(*) AS cnt,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount_cents END), 0) AS exp_c,
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount_cents END), 0) AS inc_c
            FROM transactions
            WHERE user_id = ?
            """
            + where_sql
            + """
            GROUP BY SUBSTR(transacted_on, 1, 7)
            ORDER BY y DESC, m DESC
            """,
            (user.id, *where_params),
        ).fetchall()
    groups = []
    for r in rows:
        exp = from_cents(int(r["exp_c"]))
        inc = from_cents(int(r["inc_c"]))
        groups.append(
            GroupSummaryOut(
                year=int(r["y"]),
                month=int(r["m"]),
                total_expense=exp,
                total_income=inc,
                net=inc - exp,
                count=int(r["cnt"]),
            ).model_dump()
        )
    return {"groups": groups, "total_groups": len(groups), "total_records": int(count_row["cnt"])}


@app.get("/api/transactions")
def api_list(
    year: int | None = None,
    month: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    where_sql, where_params = _tx_where_suffix(
        year, month, start_date, end_date, keyword
    )
    offset = (page - 1) * page_size
    with get_conn() as conn:
        total = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?" + where_sql,
                (user.id, *where_params),
            ).fetchone()["n"]
        )
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ?
            """
            + where_sql
            + """
            ORDER BY transacted_on DESC, created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (user.id, *where_params, page_size, offset),
        ).fetchall()
    return {
        "items": [row_to_tx(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/transactions/export")
def api_transactions_export(
    year: int | None = None,
    month: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    keyword: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    where_sql, where_params = _tx_where_suffix(
        year, month, start_date, end_date, keyword
    )
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM transactions
            WHERE user_id = ?
            """
            + where_sql
            + """
            ORDER BY transacted_on DESC, created_at DESC, id DESC
            """,
            (user.id, *where_params),
        ).fetchall()
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(
        [
            "类型",
            "金额(元)",
            "交易日期",
            "备注",
            "导入平台",
            "外部单号",
            "分类",
            "交易对方",
            "商品说明",
            "支付方式",
            "商户单号",
            "导出备注",
            "创建时间",
        ]
    )
    plat_map = {"alipay": "支付宝", "wechat": "微信"}
    type_map = {"expense": "消费", "income": "收入"}
    for r in rows:
        plat = r["import_platform"]
        plat_zh = plat_map.get(plat, plat or "")
        w.writerow(
            [
                type_map.get(r["type"], r["type"]),
                from_cents(int(r["amount_cents"])),
                r["transacted_on"] or "",
                r["note"] or "",
                plat_zh,
                r["external_id"] or "",
                r["bill_category"] or "",
                r["bill_counterparty"] or "",
                r["bill_product"] or "",
                r["bill_payment_method"] or "",
                r["bill_merchant_no"] or "",
                r["bill_export_note"] or "",
                r["created_at"] or "",
            ]
        )
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ledger-export.csv"'},
    )


@app.post("/api/transactions")
def api_create(body: TransactionCreate, user: CurrentUser = Depends(get_current_user)):
    now = _now_iso()
    transacted_on = body.transacted_on or _today_date()
    try:
        ac = to_cents(body.amount)
        datetime.strptime(transacted_on, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO transactions
            (user_id, type, amount_cents, note, transacted_on, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user.id, body.type, ac, body.note.strip(), transacted_on, now, now),
        )
        tid = cur.lastrowid
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (tid, user.id),
        ).fetchone()
    return row_to_tx(row)


@app.post("/api/transactions/import")
async def api_import(
    platform: str = Form(...),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    if platform not in ("alipay", "wechat"):
        raise HTTPException(status_code=400, detail="platform 须为 alipay 或 wechat")
    fn = (file.filename or "").lower()
    raw = await file.read()
    max_bytes = 15 * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail="文件过大（上限 15MB）")

    if platform == "alipay":
        if not fn.endswith(".csv"):
            raise HTTPException(
                status_code=400, detail="支付宝导入须上传 .csv 交易明细文件"
            )
        parsed, err = bill_import.parse_alipay_csv(raw)
    else:
        if not fn.endswith(".xlsx"):
            raise HTTPException(
                status_code=400, detail="微信导入须上传 .xlsx 微信支付账单流水文件"
            )
        parsed, err = bill_import.parse_wechat_xlsx(raw)

    if err or parsed is None:
        raise HTTPException(status_code=400, detail=err or "解析失败")

    now = _now_iso()
    inserted = 0
    skipped_duplicate = 0
    with get_conn() as conn:
        existing_rows = conn.execute(
            """
            SELECT import_platform, external_id FROM transactions
            WHERE user_id = ? AND import_platform IS NOT NULL AND external_id IS NOT NULL
            """,
            (user.id,),
        ).fetchall()
        existing = {(r["import_platform"], r["external_id"]) for r in existing_rows}

        for br in parsed.rows:
            key = (platform, br.external_id)
            if key in existing:
                skipped_duplicate += 1
                continue
            conn.execute(
                """
                INSERT INTO transactions (
                    user_id, type, amount_cents, note, transacted_on,
                    created_at, updated_at,
                    import_platform, external_id,
                    bill_category, bill_counterparty, bill_product,
                    bill_payment_method, bill_merchant_no, bill_export_note
                ) VALUES (?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user.id,
                    br.type,
                    br.amount_cents,
                    br.transacted_on,
                    now,
                    now,
                    platform,
                    br.external_id,
                    br.bill_category or None,
                    br.bill_counterparty or None,
                    br.bill_product or None,
                    br.bill_payment_method or None,
                    br.bill_merchant_no or None,
                    br.bill_export_note or None,
                ),
            )
            inserted += 1
            existing.add(key)

    return {
        "ok": True,
        "inserted": inserted,
        "skipped_duplicate": skipped_duplicate,
        "skipped_neutral": parsed.skipped_neutral,
        "skipped_bad_status": parsed.skipped_bad_status,
        "skipped_zero_amount": parsed.skipped_zero_amount,
        "skipped_no_date": parsed.skipped_no_date,
        "skipped_no_external_id": parsed.skipped_no_external_id,
        "total_parsed": len(parsed.rows),
    }


@app.patch("/api/transactions/{tx_id}")
def api_patch(
    tx_id: int, body: TransactionPatch, user: CurrentUser = Depends(get_current_user)
):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (tx_id, user.id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        note = row["note"]
        ac = row["amount_cents"]
        tx_type = row["type"]
        transacted_on = row["transacted_on"]
        if body.note is not None:
            note = body.note.strip()
        if body.amount is not None:
            try:
                ac = to_cents(body.amount)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        if body.type is not None:
            tx_type = body.type
        if body.transacted_on is not None:
            try:
                datetime.strptime(body.transacted_on, "%Y-%m-%d")
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail="交易日期格式须为 YYYY-MM-DD"
                ) from e
            transacted_on = body.transacted_on
        now = _now_iso()
        conn.execute(
            """
            UPDATE transactions
            SET note = ?, amount_cents = ?, type = ?, transacted_on = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (note, ac, tx_type, transacted_on, now, tx_id, user.id),
        )
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (tx_id, user.id),
        ).fetchone()
    return row_to_tx(row)


@app.delete("/api/transactions/{tx_id}")
def api_delete(tx_id: int, user: CurrentUser = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (tx_id, user.id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在")
    return {"ok": True}


@app.get("/api/health")
def api_health():
    return {"ok": True}


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


app.mount(
    "/",
    StaticFiles(directory=str(STATIC_DIR), html=True),
    name="static",
)
