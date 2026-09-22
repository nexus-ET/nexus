import errno
import logging
import os
import socket
import threading
import time
from urllib.parse import urlparse

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from app.config import normalize_database_url, settings

_db_logger = logging.getLogger("nexus.db")


def is_ssh_tunnel_database_url(database_url: str) -> bool:
    """True when DATABASE_URL targets a local SSH DB forward (Hostinger :15432)."""
    url = (database_url or "").strip().lower()
    if not url or url.startswith("sqlite"):
        return False
    local_hosts = ("127.0.0.1", "localhost", "[::1]")
    if not any(h in url for h in local_hosts):
        return False
    port = (os.getenv("NEXUS_SSH_LOCAL_PORT") or "").strip() or "15432"
    return f":{port}" in url or ":15432" in url


def _engine_pool_recycle(database_url: str) -> int:
    if database_url.startswith("sqlite"):
        return 1800
    # SSH tunnels flap on Windows sleep / NAT idle; recycle well under typical idle kills.
    if is_ssh_tunnel_database_url(database_url):
        return 90
    # Neon/serverless Postgres terminates idle connections; recycle before that.
    return 300


def _engine_connect_timeout(database_url: str) -> int:
    # Hostinger via SSH often needs >20s under concurrent pool pressure; cold
    # connects alone are often 6–9s, and contended opens can exceed 20s.
    env_raw = (os.getenv("NEXUS_DB_CONNECT_TIMEOUT") or "").strip()
    if env_raw.isdigit():
        return max(1, int(env_raw))
    if is_ssh_tunnel_database_url(database_url):
        return 45
    return 10


def _engine_connect_args(database_url: str) -> dict:
    """psycopg connect kwargs — connect_timeout always; statement_timeout if configured."""
    if database_url.startswith("sqlite"):
        return {}
    # Fail fast when the SSH tunnel (or remote DB) is down instead of hanging ~minutes.
    args: dict = {"connect_timeout": _engine_connect_timeout(database_url)}
    # Keepalive knobs (libpq / psycopg3) help detect dead tunnel sockets mid-query.
    if is_ssh_tunnel_database_url(database_url):
        args["keepalives"] = 1
        args["keepalives_idle"] = 30
        args["keepalives_interval"] = 10
        args["keepalives_count"] = 3
    timeout_ms = int(getattr(settings, "PG_STATEMENT_TIMEOUT_MS", 0) or 0)
    if timeout_ms > 0:
        # Applied on every new connection (pool checkout of a fresh conn).
        args["options"] = f"-c statement_timeout={timeout_ms}"
    return args


# Belt-and-suspenders: Settings already normalizes, but re-apply so engine never
# sees Neon console channel_binding=require or bare postgresql:// (psycopg2).
_DATABASE_URL = normalize_database_url(settings.DATABASE_URL)
_IS_SSH_TUNNEL_DB = is_ssh_tunnel_database_url(_DATABASE_URL)

_TUNNEL_WAIT_HINT = (
    "powershell -ExecutionPolicy Bypass -File .\\start-hostinger-db-tunnel.ps1 "
    "(do not -ForceRestart while the backend is waiting — that kills a recovering ssh)"
)
_TUNNEL_RESTART_HINT = (
    "powershell -ExecutionPolicy Bypass -File .\\start-hostinger-db-tunnel.ps1 -ForceRestart"
)
_TUNNEL_DOWN_LOG_INTERVAL_SEC = 15.0
# Local refused is instant; 0.4s was too short after ForceRestart (TIME_WAIT /
# ssh still binding) and was logged as "not listening" when the real failure
# was ConnectionTimeout (forward accepting, remote Postgres still warming).
_TUNNEL_TCP_PROBE_SEC = 1.0
_TUNNEL_CLOSED_ERROR_AFTER = 3
_last_tunnel_down_log_monotonic = 0.0
_tunnel_closed_streak = 0
_in_db_wait = threading.local()
_tunnel_recover_lock = threading.Lock()
_tunnel_recover_in_progress = False
_tunnel_recover_waiters = threading.Event()
_tunnel_recover_waiters.set()
_tunnel_recover_ok = True
# Cap simultaneous new TCP opens through one Windows ssh.exe forward.
_TUNNEL_CONNECT_GATE = threading.Semaphore(3)
_SCANX_DB_SLOTS = threading.BoundedSemaphore(2 if _IS_SSH_TUNNEL_DB else 8)
# Jobs wait in line (OCR already ran); API GETs keep a short slot wait.
_SCANX_SLOT_TIMEOUT_SEC = 120.0 if _IS_SSH_TUNNEL_DB else 30.0
# Fail-fast for SPA (/me). ScanX jobs use the long value via thread-local.
_API_CONNECT_GATE_TIMEOUT_SEC = 12.0
_SCANX_CONNECT_GATE_TIMEOUT_SEC = 120.0
_scanx_long_connect_gate = threading.local()


def ssh_tunnel_local_port() -> int:
    raw = (os.getenv("NEXUS_SSH_LOCAL_PORT") or "").strip()
    if raw.isdigit():
        return int(raw)
    return 15432


def _classify_tunnel_tcp_error(exc: BaseException) -> str:
    """Map a TCP OSError to 'closed' (refused) or 'warming' (timeout/reset)."""
    if isinstance(exc, ConnectionRefusedError):
        return "closed"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "warming"
    err = getattr(exc, "winerror", None)
    if err is None:
        err = getattr(exc, "errno", None)
    # Windows WSA* plus POSIX. Timeout/reset ≠ nothing listening.
    if err in (errno.ECONNREFUSED, 10061):
        return "closed"
    return "warming"


def probe_ssh_tunnel_tcp(*, timeout: float | None = None) -> str:
    """Return 'up', 'closed' (connection refused), or 'warming' (timeout/reset).

    Uses connect, never bind — binding would race ssh.exe for :15432.
    A TCP timeout is not 'closed': after ForceRestart the port can sit in
    TIME_WAIT, and a live -L forward can accept slowly while Postgres warms.
    """
    global _tunnel_closed_streak
    if not _IS_SSH_TUNNEL_DB:
        _tunnel_closed_streak = 0
        return "up"
    wait = _TUNNEL_TCP_PROBE_SEC if timeout is None else timeout
    try:
        with socket.create_connection(("127.0.0.1", ssh_tunnel_local_port()), timeout=wait):
            _tunnel_closed_streak = 0
            return "up"
    except OSError as exc:
        state = _classify_tunnel_tcp_error(exc)
        if state == "closed":
            _tunnel_closed_streak += 1
        else:
            _tunnel_closed_streak = 0
        return state


def is_ssh_tunnel_tcp_up(*, timeout: float | None = None) -> bool:
    """True when 127.0.0.1:<ssh-local-port> completed a TCP handshake."""
    return probe_ssh_tunnel_tcp(timeout=timeout) == "up"


def log_ssh_tunnel_down(*, detail: str = "", state: str = "closed") -> None:
    """Rate-limited tunnel status. WARNING while warming or early refused.

    ERROR only when the port is truly refused for several consecutive probes
    and we are not inside wait_for_database. Never suggests -ForceRestart
    during bootstrap wait (that drops a recovering ssh).
    """
    global _last_tunnel_down_log_monotonic
    now = time.monotonic()
    if (
        _last_tunnel_down_log_monotonic
        and now - _last_tunnel_down_log_monotonic < _TUNNEL_DOWN_LOG_INTERVAL_SEC
    ):
        return
    _last_tunnel_down_log_monotonic = now
    extra = f" ({detail})" if detail else ""
    port = ssh_tunnel_local_port()
    in_wait = bool(getattr(_in_db_wait, "active", False))
    truly_closed = state == "closed" and _tunnel_closed_streak >= _TUNNEL_CLOSED_ERROR_AFTER

    if state == "warming":
        _db_logger.warning(
            "[db-tunnel] SSH tunnel still warming on 127.0.0.1:%s%s — "
            "wait for the start-dev watchdog; do not -ForceRestart mid-bootstrap. Hint: %s",
            port,
            extra,
            _TUNNEL_WAIT_HINT,
        )
        return
    if truly_closed and not in_wait:
        _db_logger.error(
            "[db-tunnel] SSH tunnel is down on 127.0.0.1:%s%s — restart: %s",
            port,
            extra,
            _TUNNEL_RESTART_HINT,
        )
        return
    _db_logger.warning(
        "[db-tunnel] SSH tunnel not listening yet on 127.0.0.1:%s%s — waiting. %s",
        port,
        extra,
        _TUNNEL_WAIT_HINT,
    )


def _quick_select1(*, timeout: int = 4) -> bool:
    """One-off SELECT 1 that does not use the SQLAlchemy pool."""
    import psycopg
    from sqlalchemy.engine.url import make_url

    url = make_url(_DATABASE_URL)
    try:
        conn = psycopg.connect(
            host=url.host,
            port=url.port or 5432,
            dbname=url.database,
            user=url.username,
            password=url.password,
            connect_timeout=max(1, int(timeout)),
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        finally:
            conn.close()
    except Exception:
        return False


def recover_ssh_tunnel(*, reason: str = "") -> bool:
    """Single-flight wait until TCP + SELECT 1 succeed (or ~12s). Stampede-safe.

    Does not spawn ssh.exe — start-dev.ps1 / start-hostinger-db-tunnel.ps1
    watchdog owns the single :15432 forward. A second -L here would dual-bind
    and ForceRestart would drop a tunnel that is already recovering.
    """
    global _tunnel_recover_in_progress, _tunnel_recover_ok
    if not _IS_SSH_TUNNEL_DB:
        return True
    if probe_ssh_tunnel_tcp() == "up" and _quick_select1(timeout=3):
        return True

    with _tunnel_recover_lock:
        if _tunnel_recover_in_progress:
            waiter = True
        else:
            waiter = False
            _tunnel_recover_in_progress = True
            _tunnel_recover_waiters.clear()

    if waiter:
        _tunnel_recover_waiters.wait(timeout=20)
        return bool(_tunnel_recover_ok)

    ok = False
    try:
        tcp = probe_ssh_tunnel_tcp()
        if tcp != "up":
            log_ssh_tunnel_down(detail=reason or tcp, state=tcp)
        dispose_db_pool(reason=reason or "tunnel recover")
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            tcp = probe_ssh_tunnel_tcp()
            if tcp != "up":
                log_ssh_tunnel_down(detail=reason or tcp, state=tcp)
                time.sleep(0.6)
                continue
            if _quick_select1(timeout=4):
                dispose_db_pool(reason=f"recovered {reason}".strip())
                ok = True
                break
            time.sleep(0.6)
        if not ok:
            tcp = probe_ssh_tunnel_tcp()
            if tcp != "up":
                log_ssh_tunnel_down(detail=reason or "SELECT 1 failed", state=tcp)
            else:
                _db_logger.warning(
                    "[db-tunnel] SELECT 1 failed with port listening (%s)",
                    reason or "tunnel recover",
                )
        _tunnel_recover_ok = ok
        return ok
    finally:
        with _tunnel_recover_lock:
            _tunnel_recover_in_progress = False
            _tunnel_recover_waiters.set()


def connect_gate_timeout_sec() -> float:
    """Seconds to wait for a new-TCP slot through ssh.exe.

    API / SPA checkouts fail fast (12s) so /users/me is not pinned behind OCR.
    ScanX job threads wait much longer — enhance/classify already finished and
    the file is fine; a 12s leftover must not mark the document failed.
    """
    if getattr(_scanx_long_connect_gate, "active", False):
        return _SCANX_CONNECT_GATE_TIMEOUT_SEC
    return _API_CONNECT_GATE_TIMEOUT_SEC


def open_scanx_session(*, timeout: float | None = None, optional: bool = False):
    """SessionLocal checkout that cannot take more than the ScanX slot cap.

    On the SSH tunnel this reserves pool capacity for SPA GETs (/me, permissions).
    Job checkouts (default timeout) also opt into the long connect-gate wait so
    a busy ssh.exe forward queues OCR resume instead of TimeoutError.
    Heartbeats use a short optional timeout and keep the API fail-fast gate.
    """
    wait = _SCANX_SLOT_TIMEOUT_SEC if timeout is None else timeout
    got = _SCANX_DB_SLOTS.acquire(timeout=max(0.0, wait))
    if not got:
        if optional:
            return None
        raise TimeoutError("ScanX DB slot timeout")
    # Optional/short checkouts (OCR heartbeats) must not hold the SPA fail-fast
    # gate for 120s. Job sessions stay flagged until safe_close_session so a
    # lazy first execute still gets the long wait.
    long_gate = (not optional) and wait >= 15.0
    if long_gate:
        _scanx_long_connect_gate.active = True
    try:
        db = SessionLocal()
        db.info["_scanx_slot"] = True
        db.info["_scanx_long_gate"] = long_gate
        return db
    except Exception:
        if long_gate:
            _scanx_long_connect_gate.active = False
        _SCANX_DB_SLOTS.release()
        raise


# Pool notes for remote / SSH-tunnel Postgres:
# - pool_pre_ping=True discards dead conns after tunnel flap (SELECT 1 on checkout).
# - pool_recycle=90 (tunnel) / 300 (other) refreshes sockets before NAT/SSH idle kills.
# - connect_timeout=20 (tunnel, override via NEXUS_DB_CONNECT_TIMEOUT) balances
#   fail-fast vs Hostinger RTT spikes that used to false-timeout at 5s.
# - Prefer backend-on-VPS or firewall-to-home-IP when developing against Hostinger
#   (tunnel RTT is often 200–500 ms per query).
# - Direct/local Postgres: pool_size=15 / max_overflow=25 for ScanX threads.
# - SSH tunnel: keep the multiplex modest (default 5+5). Opening 40 sockets through
#   one Windows ssh.exe forward saturates the tunnel → ConnectionTimeout storms
#   on cheap GETs like /leads/{id}/followups. 3+2 was too tight for document-readiness
#   (ScanX list + FlowX master strip + prospects typeahead + inbox in parallel).
#   Override via NEXUS_DB_POOL_SIZE / NEXUS_DB_MAX_OVERFLOW if needed.
def _engine_pool_size(database_url: str) -> tuple[int, int, int]:
    """Return (pool_size, max_overflow, pool_timeout)."""
    size_env = (os.getenv("NEXUS_DB_POOL_SIZE") or "").strip()
    overflow_env = (os.getenv("NEXUS_DB_MAX_OVERFLOW") or "").strip()
    timeout_env = (os.getenv("NEXUS_DB_POOL_TIMEOUT") or "").strip()
    if is_ssh_tunnel_database_url(database_url):
        size = int(size_env) if size_env.isdigit() else 5
        overflow = int(overflow_env) if overflow_env.isdigit() else 5
        # Fail fast so SPA GETs get 503 (and retry) instead of hanging to AbortError.
        # Silent ScanX polls budget ~20s; 12s leaves room for one client retry.
        timeout = int(timeout_env) if timeout_env.isdigit() else 12
    else:
        size = int(size_env) if size_env.isdigit() else 15
        overflow = int(overflow_env) if overflow_env.isdigit() else 25
        timeout = int(timeout_env) if timeout_env.isdigit() else 30
    return max(1, size), max(0, overflow), max(5, timeout)


DB_TEMPORARILY_BUSY_DETAIL = "Database temporarily busy; retry shortly."
DB_TEMPORARILY_BUSY_RETRY_AFTER = "2"


def db_temporarily_busy_headers() -> dict[str, str]:
    """Advise clients to wait briefly before retrying a 503 pool/tunnel miss."""
    return {"Retry-After": DB_TEMPORARILY_BUSY_RETRY_AFTER}


def is_db_pool_pressure_error(exc_or_text: BaseException | str) -> bool:
    """True when SQLAlchemy could not check out a pooled connection in time."""
    if isinstance(exc_or_text, BaseException):
        try:
            from sqlalchemy.exc import TimeoutError as SATimeoutError

            if isinstance(exc_or_text, SATimeoutError):
                return True
        except Exception:
            pass
    text = str(exc_or_text).lower()
    return any(
        needle in text
        for needle in (
            "queuepool",
            "pool limit of size",
            "connection timed out, timeout",
            "scanx db slot timeout",
            "tunnel connect gate busy",
        )
    )


def should_dispose_pool_for_error(exc_or_text: BaseException | str) -> bool:
    """Dispose pooled sockets after a tunnel flap — not after QueuePool wait timeout.

    Pool timeout means connections are still in use. Disposing them kills in-flight
    work and triggers a reconnect storm through the SSH tunnel.
    """
    if is_db_pool_pressure_error(exc_or_text):
        return False
    return is_db_tunnel_transient_error(exc_or_text)


_TUNNEL_TRANSIENT_NEEDLES = (
    "server closed the connection",
    "connection refused",
    "could not connect",
    "connection timeout",
    "timeout expired",
    "consuming input failed",
    "ssl connection has been closed",
    "connection reset by peer",
    "broken pipe",
    "can't reconnect until invalid transaction",
    "pendingrollbackerror",
    "the connection is closed",
    "connection is lost",
    "network is unreachable",
    # Postgres AdminShutdown / host kill — retryable disconnect, not app logic.
    "adminshutdown",
    "administrator command",
    "terminating connection due to",
)


def _iter_tunnel_exceptions(exc: BaseException):
    """Yield an exception plus its cause chain, DBAPI ``orig``, and ExceptionGroup members."""
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        orig = getattr(current, "orig", None)
        if isinstance(orig, BaseException):
            stack.append(orig)
        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            stack.append(cause)
        nested = getattr(current, "exceptions", None)
        if nested:
            for sub in nested:
                if isinstance(sub, BaseException):
                    stack.append(sub)


def is_db_tunnel_transient_error(exc_or_text: BaseException | str) -> bool:
    """True for Hostinger SSH-tunnel flaps / Postgres dropping the socket mid-query.

    These are infrastructure noise during local ``start-dev`` — return 503 and do
    not email Exception Report (same treatment as pool pressure).
    """
    if is_db_pool_pressure_error(exc_or_text):
        return True
    if isinstance(exc_or_text, BaseException):
        parts = [str(part) for part in _iter_tunnel_exceptions(exc_or_text)]
        text = "\n".join(parts).lower()
        try:
            from sqlalchemy.exc import PendingRollbackError

            if any(isinstance(part, PendingRollbackError) for part in _iter_tunnel_exceptions(exc_or_text)):
                return True
        except Exception:
            pass
    else:
        text = str(exc_or_text).lower()
    return any(needle in text for needle in _TUNNEL_TRANSIENT_NEEDLES)


def install_quiet_tunnel_logging() -> None:
    """Stop SSH-tunnel drops from printing multi-page tracebacks.

    Starlette's ServerErrorMiddleware re-raises after the 503 handler, so uvicorn
    logs ``Exception in ASGI application`` with a full stack. SQLAlchemy's pool
    does the same for ``Exception during reset`` when ROLLBACK hits a dead socket.
    The request still fails; the stack is not actionable.
    """
    if getattr(install_quiet_tunnel_logging, "_installed", False):
        return
    original_handle = logging.Logger.handle

    def handle(self: logging.Logger, record: logging.LogRecord) -> None:
        exc = record.exc_info[1] if record.exc_info and record.exc_info[1] is not None else None
        if exc is not None and is_db_tunnel_transient_error(exc):
            text = record.msg if isinstance(record.msg, str) else ""
            if (
                "Exception in ASGI application" in text
                or "Exception during reset" in text
                or "closing connection" in text
                or "terminating connection" in text
            ):
                return
            record.exc_info = None
            record.exc_text = None
            if record.levelno >= logging.ERROR:
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
        original_handle(self, record)

    logging.Logger.handle = handle  # type: ignore[method-assign]
    install_quiet_tunnel_logging._installed = True  # type: ignore[attr-defined]


_POOL_SIZE, _MAX_OVERFLOW, _POOL_TIMEOUT = _engine_pool_size(_DATABASE_URL)


def _psycopg_connect_with_retry():
    """Open a psycopg connection; retry briefly on SSH-tunnel timeouts.

    Fail-fast (2s) only when the local port is truly refused. A TCP timeout
    means the forward may still be warming — do not log "port not listening"
    and do not cut connect_timeout to 2s (that turns a slow ssh into
    ConnectionTimeout). Concurrent new opens are gated so a SPA stampede
    cannot saturate one Windows ssh.exe forward.
    """
    import psycopg
    from sqlalchemy.engine.url import make_url

    url = make_url(_DATABASE_URL)
    kwargs: dict = {
        "host": url.host,
        "port": url.port or 5432,
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        **_engine_connect_args(_DATABASE_URL),
    }
    attempts = 3 if _IS_SSH_TUNNEL_DB else 1
    last_exc: BaseException | None = None
    gate_held = False
    if _IS_SSH_TUNNEL_DB:
        gate_timeout = connect_gate_timeout_sec()
        gate_held = _TUNNEL_CONNECT_GATE.acquire(timeout=gate_timeout)
        if not gate_held:
            raise TimeoutError("tunnel connect gate busy")
    try:
        for attempt in range(1, attempts + 1):
            attempt_kwargs = dict(kwargs)
            tcp_state = "up"
            if _IS_SSH_TUNNEL_DB:
                tcp_state = probe_ssh_tunnel_tcp()
                if tcp_state == "closed":
                    log_ssh_tunnel_down(
                        detail="port closed before connect",
                        state="closed",
                    )
                    attempt_kwargs["connect_timeout"] = 2
                elif tcp_state == "warming":
                    log_ssh_tunnel_down(
                        detail="TCP timeout before connect (not closed)",
                        state="warming",
                    )
                    # Keep enough time for a recovering -L; 2s was a false timeout.
                    attempt_kwargs["connect_timeout"] = min(
                        int(attempt_kwargs.get("connect_timeout") or 8), 8
                    )
                elif attempt > 1:
                    # After a timeout/reset, fail faster so request retry can wait
                    # for the start-dev watchdog instead of blocking 45s again.
                    attempt_kwargs["connect_timeout"] = min(
                        int(attempt_kwargs.get("connect_timeout") or 8), 8
                    )
            try:
                return psycopg.connect(**attempt_kwargs)
            except Exception as exc:  # noqa: BLE001 — surface after retries
                last_exc = exc
                msg = str(exc).lower()
                retryable = any(
                    n in msg
                    for n in (
                        "connection timeout",
                        "timeout expired",
                        "server closed the connection",
                        "connection refused",
                        "could not connect",
                        "connection is closed",
                        "connection is lost",
                        "broken pipe",
                        "connection reset",
                    )
                )
                if not retryable or attempt >= attempts:
                    if _IS_SSH_TUNNEL_DB:
                        tcp_after = probe_ssh_tunnel_tcp()
                        if tcp_after != "up":
                            log_ssh_tunnel_down(
                                detail=type(exc).__name__,
                                state=tcp_after,
                            )
                    raise
                _db_logger.warning(
                    "[db-tunnel] connect attempt %s/%s failed (%s)%s; retrying",
                    attempt,
                    attempts,
                    type(exc).__name__,
                    ""
                    if tcp_state != "up"
                    else " — port is listening, remote Postgres still warming",
                )
                time.sleep(0.8 if tcp_state == "closed" else 1.5 * attempt)
        assert last_exc is not None
        raise last_exc
    finally:
        if gate_held:
            _TUNNEL_CONNECT_GATE.release()


engine = create_engine(
    _DATABASE_URL,
    pool_size=_POOL_SIZE,
    max_overflow=_MAX_OVERFLOW,
    pool_timeout=_POOL_TIMEOUT,
    pool_recycle=_engine_pool_recycle(_DATABASE_URL),
    pool_pre_ping=True,
    # Tunnel: custom creator (retries). Direct DB: default connect + connect_args.
    **(
        {"creator": _psycopg_connect_with_retry}
        if _IS_SSH_TUNNEL_DB
        else {"connect_args": _engine_connect_args(_DATABASE_URL)}
    ),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Global dispose throttle — concurrent ScanX heartbeats + health checks used to
# dispose on every ConnectionTimeout, wiping healthy sockets and causing a
# reconnect storm through the SSH tunnel (GET /scanx/documents 500s).
_POOL_DISPOSE_MIN_INTERVAL_SEC = 45.0
_pool_dispose_lock = threading.Lock()
_last_pool_dispose_monotonic = 0.0


def dispose_db_pool(*, reason: str = "", force: bool = False) -> bool:
    """Drop pooled connections after tunnel flap. Rate-limited unless force=True.

    Returns True when dispose actually ran.
    """
    global _last_pool_dispose_monotonic
    detail = f" ({reason})" if reason else ""
    with _pool_dispose_lock:
        now = time.monotonic()
        elapsed = now - _last_pool_dispose_monotonic
        if (
            not force
            and _last_pool_dispose_monotonic > 0
            and elapsed < _POOL_DISPOSE_MIN_INTERVAL_SEC
        ):
            _db_logger.info(
                "[db-tunnel] skip pool dispose%s — last dispose %.1fs ago (min %.0fs)",
                detail,
                elapsed,
                _POOL_DISPOSE_MIN_INTERVAL_SEC,
            )
            return False
        _db_logger.warning("[db-tunnel] disposing SQLAlchemy pool%s", detail)
        engine.dispose()
        _last_pool_dispose_monotonic = now
        return True


def wait_for_database(
    *,
    attempts: int | None = None,
    delay_sec: float | None = None,
    dispose_between: bool = True,
) -> None:
    """Block until SELECT 1 succeeds. Raises OperationalError after exhausting attempts.

    For SSH-tunnel DATABASE_URL defaults to many retries so start-dev / uvicorn
    do not accept work against a dead :15432. Early failures are WARNING; ERROR
    only after all attempts (do not -ForceRestart while this wait is running).
    """
    if _DATABASE_URL.startswith("sqlite"):
        return

    if attempts is None:
        attempts = 60 if _IS_SSH_TUNNEL_DB else 15
    if delay_sec is None:
        delay_sec = 2.0 if _IS_SSH_TUNNEL_DB else 1.0

    host = "db"
    try:
        parsed = urlparse(_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1))
        host = f"{parsed.hostname or '?'}:{parsed.port or 5432}"
    except Exception:
        pass

    _in_db_wait.active = True
    last_exc: BaseException | None = None
    try:
        for i in range(1, max(1, attempts) + 1):
            try:
                if dispose_between and i > 1:
                    engine.dispose()
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                if _IS_SSH_TUNNEL_DB:
                    _db_logger.info(
                        "[db-tunnel] healthy SELECT 1 via %s (attempt %s)", host, i
                    )
                else:
                    _db_logger.info("Database ready (%s) on attempt %s", host, i)
                return
            except (OperationalError, DBAPIError, OSError) as exc:
                last_exc = exc
                _db_logger.warning(
                    "[db-tunnel] waiting for database %s (attempt %s/%s): %s",
                    host,
                    i,
                    attempts,
                    type(exc).__name__,
                )
                time.sleep(max(0.2, delay_sec))

        assert last_exc is not None
        tcp = probe_ssh_tunnel_tcp() if _IS_SSH_TUNNEL_DB else "up"
        hint = _TUNNEL_RESTART_HINT if tcp == "closed" else _TUNNEL_WAIT_HINT
        _db_logger.error(
            "[db-tunnel] giving up after %s attempts — is the SSH tunnel up? Run: %s",
            attempts,
            hint,
        )
        raise last_exc
    finally:
        _in_db_wait.active = False


@event.listens_for(engine, "handle_error")
def _mark_tunnel_disconnect(context) -> None:  # type: ignore[no-untyped-def]
    """Treat SSH-tunnel timeouts as disconnects so the pool drops the dead socket."""
    if not _IS_SSH_TUNNEL_DB:
        return
    exc = context.original_exception
    if exc is None:
        return
    msg = str(exc).lower()
    if any(
        needle in msg
        for needle in (
            "connection timeout",
            "timeout expired",
            "server closed the connection",
            "connection refused",
            "could not connect",
            "broken pipe",
            "connection reset",
        )
    ):
        context.is_disconnect = True


def init_db():
    from app.models.lead import Lead
    from app.models.message import Message

    Base.metadata.create_all(bind=engine)


def _column_type_name(inspector, table_name: str, column_name: str) -> str:
    for column in inspector.get_columns(table_name):
        if column["name"] == column_name:
            return str(column["type"]).upper()
    return ""


def _is_text_column(type_name: str) -> bool:
    return "VARCHAR" in type_name or "CHARACTER VARYING" in type_name or type_name == "TEXT"


class _SchemaSnapshot:
    """Lazy schema introspection — one table list, cached per-table columns."""

    def __init__(self, db_engine):
        self._engine = db_engine
        self._inspector = inspect(db_engine)
        self._tables: set[str] | None = None
        self._columns: dict[str, dict[str, dict]] = {}

    def has_table(self, name: str) -> bool:
        return name in self._table_names()

    def column_names(self, name: str) -> set[str]:
        return set(self.columns(name).keys())

    def columns(self, name: str) -> dict[str, dict]:
        if name not in self._columns:
            if not self.has_table(name):
                self._columns[name] = {}
            else:
                self._columns[name] = {
                    col["name"]: col for col in self._inspector.get_columns(name)
                }
        return self._columns[name]

    def column_type_name(self, table: str, column: str) -> str:
        col = self.columns(table).get(column)
        return str(col["type"]).upper() if col else ""

    def refresh(self) -> None:
        self._tables = None
        self._columns.clear()
        self._inspector = inspect(self._engine)

    def drop_table(self, name: str) -> None:
        self._table_names().discard(name)
        self._columns.pop(name, None)

    def note_table(self, name: str) -> None:
        self._table_names().add(name)
        self._columns.pop(name, None)

    def _table_names(self) -> set[str]:
        if self._tables is None:
            self._tables = set(self._inspector.get_table_names())
        return self._tables


def sync_schema_columns() -> None:
    """Add or rename columns that create_all() cannot backfill on existing tables."""
    snap = _SchemaSnapshot(engine)
    _ensure_institution_types_catalog()

    if snap.has_table("leads"):
        lead_columns = snap.column_names("leads")
        if "assigned_advisor_id" not in lead_columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE leads ADD COLUMN assigned_advisor_id INTEGER "
                        "REFERENCES users(id)"
                    )
                )

        intake_columns = {
            "intake_step": "VARCHAR(50)",
            "current_location": "VARCHAR(255)",
            "english_test_scores": "VARCHAR(100)",
            "gre_score": "VARCHAR(50)",
            "gmat_score": "VARCHAR(50)",
            "wants_consultation_call": "BOOLEAN",
            "consultation_scheduled_at": "TIMESTAMP",
            "intake_context": "TEXT",
        }
        lead_columns = snap.column_names("leads")
        with engine.begin() as conn:
            for column_name, column_type in intake_columns.items():
                if column_name not in lead_columns:
                    conn.execute(
                        text(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
                    )

    if not snap.has_table("users"):
        return

    user_columns = snap.column_names("users")

    with engine.begin() as conn:
        if "status_change_reason_id" in user_columns and "activation_reason" not in user_columns:
            conn.execute(
                text("ALTER TABLE users RENAME COLUMN status_change_reason_id TO activation_reason")
            )
            user_columns.remove("status_change_reason_id")
            user_columns.add("activation_reason")

        if "status_changed_at" in user_columns and "activation_date" not in user_columns:
            conn.execute(
                text("ALTER TABLE users RENAME COLUMN status_changed_at TO activation_date")
            )
            user_columns.remove("status_changed_at")
            user_columns.add("activation_date")

        if "creation_reason" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN creation_reason INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )

        if "creation_date" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN creation_date TIMESTAMP"))

        if "deactivation_reason" in user_columns and _is_text_column(
            snap.column_type_name("users", "deactivation_reason")
        ):
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN deactivation_reason_fk INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET deactivation_reason_fk = scr.id
                    FROM status_change_reason scr
                    WHERE scr.reason_type = 'Deactivate'
                      AND scr.reason = u.deactivation_reason
                      AND u.deactivation_reason IS NOT NULL
                      AND btrim(u.deactivation_reason) <> ''
                    """
                )
            )
            conn.execute(text("ALTER TABLE users DROP COLUMN deactivation_reason"))
            conn.execute(
                text("ALTER TABLE users RENAME COLUMN deactivation_reason_fk TO deactivation_reason")
            )
            user_columns.discard("deactivation_reason")
            user_columns.add("deactivation_reason")

        if "deactivation_reason" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN deactivation_reason INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )

        if "deactivation_date" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN deactivation_date TIMESTAMP"))

        if "activation_reason" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN activation_reason INTEGER "
                    "REFERENCES status_change_reason(id)"
                )
            )

        if "activation_date" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN activation_date TIMESTAMP"))

        if "admin_role_id" not in user_columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN admin_role_id INTEGER "
                    "REFERENCES admin_roles(id)"
                )
            )
            user_columns.add("admin_role_id")

        if "phone_number" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN phone_number VARCHAR(50)"))

        if "role" in user_columns and _is_text_column(
            snap.column_type_name("users", "role")
        ):
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND lower(btrim(u.role)) = lower(btrim(ar.name))
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND lower(btrim(u.role)) IN ('admin', 'web admin')
                      AND ar.name = 'Web Admin'
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND lower(btrim(u.role)) = 'super admin'
                      AND ar.name = 'Super Admin'
                    """
                )
            )
            conn.execute(text("ALTER TABLE users DROP COLUMN role"))
            user_columns.discard("role")

        if "admin_role_id" in user_columns:
            conn.execute(
                text(
                    """
                    UPDATE users u
                    SET admin_role_id = ar.id
                    FROM admin_roles ar
                    WHERE u.admin_role_id IS NULL
                      AND ar.name = 'Web Admin'
                    """
                )
            )

    snap.refresh()

    if snap.has_table("navigation_pages"):
        nav_columns = snap.column_names("navigation_pages")
        with engine.begin() as conn:
            if "icon" not in nav_columns:
                conn.execute(text("ALTER TABLE navigation_pages ADD COLUMN icon VARCHAR(50)"))
            if "sort_order" not in nav_columns:
                conn.execute(
                    text("ALTER TABLE navigation_pages ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
                )
            if "is_active" not in nav_columns:
                conn.execute(
                    text(
                        "ALTER TABLE navigation_pages ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
                    )
                )

    if snap.has_table("role_page_permissions"):
        perm_columns = snap.column_names("role_page_permissions")
        required_perm_columns = {"admin_role_id", "navigation_page_id", "can_access"}
        if not required_perm_columns.issubset(perm_columns):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS role_page_permissions"))
            snap.drop_table("role_page_permissions")

    snap.refresh()
    if not snap.has_table("role_page_permissions"):
        from app.models.role_page_permission import RolePagePermission

        RolePagePermission.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("role_page_permissions")

    snap.refresh()

    if snap.has_table("counselling_bookings"):
        booking_columns = snap.column_names("counselling_bookings")
        with engine.begin() as conn:
            if "scheduled_time" not in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ADD COLUMN scheduled_time TIMESTAMP")
                )
                if "slot_id" in booking_columns and snap.has_table("counselling_slots"):
                    conn.execute(
                        text(
                            """
                            UPDATE counselling_bookings cb
                            SET scheduled_time = cs.start_time
                            FROM counselling_slots cs
                            WHERE cb.slot_id = cs.id
                              AND cb.scheduled_time IS NULL
                            """
                        )
                    )
                conn.execute(
                    text(
                        """
                        UPDATE counselling_bookings
                        SET scheduled_time = COALESCE(updated_at, created_at, NOW())
                        WHERE scheduled_time IS NULL
                        """
                    )
                )
                conn.execute(
                    text("ALTER TABLE counselling_bookings ALTER COLUMN scheduled_time SET NOT NULL")
                )
                booking_columns.add("scheduled_time")

            if "candidate_email" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN candidate_email VARCHAR(255)"))
            if "candidate_phone" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN candidate_phone VARCHAR(50)"))
            if "lead_id" not in booking_columns:
                conn.execute(
                    text(
                        "ALTER TABLE counselling_bookings ADD COLUMN lead_id INTEGER "
                        "REFERENCES leads(id) ON DELETE SET NULL"
                    )
                )

            if "admin_id" in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ALTER COLUMN admin_id DROP NOT NULL")
                )

            if "slot_id" in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings DROP CONSTRAINT IF EXISTS counselling_bookings_slot_id_fkey"))
                conn.execute(text("ALTER TABLE counselling_bookings DROP COLUMN IF EXISTS slot_id"))

            conn.execute(
                text(
                    """
                    UPDATE counselling_bookings
                    SET status = 'PENDING'
                    WHERE admin_id IS NULL
                      AND upper(status) NOT IN ('CANCELLED', 'SCHEDULED')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE counselling_bookings
                    SET status = 'SCHEDULED'
                    WHERE admin_id IS NOT NULL
                      AND upper(status) NOT IN ('CANCELLED')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE counselling_bookings
                    SET status = 'CANCELLED'
                    WHERE lower(status) = 'cancelled'
                    """
                )
            )

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS counselling_slots CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS counselling_rosters CASCADE"))
    snap.drop_table("counselling_slots")
    snap.drop_table("counselling_rosters")

    snap.refresh()
    if snap.has_table("dynamic_settings"):
        setting_columns = snap.column_names("dynamic_settings")
        with engine.begin() as conn:
            if "updated_by_user_id" not in setting_columns:
                conn.execute(
                    text(
                        "ALTER TABLE dynamic_settings ADD COLUMN updated_by_user_id INTEGER "
                        "REFERENCES users(id) ON DELETE SET NULL"
                    )
                )

    snap.refresh()
    if snap.has_table("notification_logs"):
        log_columns = snap.column_names("notification_logs")
        with engine.begin() as conn:
            if "user_id" not in log_columns:
                conn.execute(
                    text(
                        "ALTER TABLE notification_logs ADD COLUMN user_id INTEGER "
                        "REFERENCES users(id) ON DELETE SET NULL"
                    )
                )
            if "title" not in log_columns:
                conn.execute(text("ALTER TABLE notification_logs ADD COLUMN title VARCHAR(255) DEFAULT ''"))
            if "message" not in log_columns:
                conn.execute(text("ALTER TABLE notification_logs ADD COLUMN message TEXT DEFAULT ''"))
            if "priority" not in log_columns:
                conn.execute(
                    text("ALTER TABLE notification_logs ADD COLUMN priority VARCHAR(20) DEFAULT 'normal'")
                )
            booking_col = snap.columns("notification_logs").get("booking_id")
            if booking_col and not booking_col.get("nullable", True):
                if engine.dialect.name == "postgresql":
                    conn.execute(text("ALTER TABLE notification_logs ALTER COLUMN booking_id DROP NOT NULL"))

    snap.refresh()
    if snap.has_table("users"):
        user_columns = snap.column_names("users")
        with engine.begin() as conn:
            if "fcm_tokens" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN fcm_tokens TEXT"))

    if not snap.has_table("businesses"):
        from app.models.business import Business

        Business.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("businesses")

    snap.refresh()
    if snap.has_table("businesses"):
        business_columns = snap.column_names("businesses")
        address_columns = {
            "address_line1": "VARCHAR(255)",
            "address_line2": "VARCHAR(255)",
            "address_line3": "VARCHAR(255)",
            "city": "VARCHAR(120)",
            "state": "VARCHAR(120)",
            "country": "VARCHAR(120)",
            "zip_code": "VARCHAR(30)",
            "office_phone_number": "VARCHAR(50)",
            "office_mobile_number": "VARCHAR(50)",
            "office_phone_active": "BOOLEAN",
            "office_mobile_active": "BOOLEAN",
            "office_phone_contacts": "JSON",
            "office_email_contacts": "JSON",
            "logo_path": "VARCHAR(500)",
        }
        with engine.begin() as conn:
            for column_name, column_type in address_columns.items():
                if column_name not in business_columns:
                    dialect = engine.dialect.name
                    sql_type = column_type
                    if column_type == "JSON" and dialect == "postgresql":
                        sql_type = "JSONB"
                    conn.execute(
                        text(f"ALTER TABLE businesses ADD COLUMN {column_name} {sql_type}")
                    )
            if "office_phone_active" not in business_columns:
                conn.execute(
                    text(
                        "UPDATE businesses SET office_phone_active = TRUE "
                        "WHERE office_phone_active IS NULL"
                    )
                )
            if "office_mobile_active" not in business_columns:
                conn.execute(
                    text(
                        "UPDATE businesses SET office_mobile_active = TRUE "
                        "WHERE office_mobile_active IS NULL"
                    )
                )
            if "address" in business_columns and "address_line1" in (
                business_columns | set(address_columns.keys())
            ):
                conn.execute(
                    text(
                        "UPDATE businesses SET address_line1 = address "
                        "WHERE address IS NOT NULL AND TRIM(address) <> '' "
                        "AND (address_line1 IS NULL OR TRIM(address_line1) = '')"
                    )
                )

    snap.refresh()
    if snap.has_table("users") and snap.has_table("businesses"):
        user_columns = snap.column_names("users")
        with engine.begin() as conn:
            if "business_id" not in user_columns:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN business_id INTEGER "
                        "REFERENCES businesses(id) DEFAULT 1"
                    )
                )
                conn.execute(text("UPDATE users SET business_id = 1 WHERE business_id IS NULL"))

    migrate_audit_logs_schema()

    snap.refresh()
    if not snap.has_table("security_audit_runs"):
        from app.models.security_audit_run import SecurityAuditRun

        SecurityAuditRun.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("security_audit_runs")

    if not snap.has_table("sync_logs"):
        from app.models.sync_log import SyncLog

        SyncLog.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("sync_logs")
    elif snap.has_table("sync_logs"):
        sync_log_columns = snap.column_names("sync_logs")
        with engine.begin() as conn:
            if "sync_mode" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN sync_mode VARCHAR(20) NOT NULL DEFAULT 'AUTOMATED'"))
            if "triggered_by_user" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN triggered_by_user VARCHAR(255) NOT NULL DEFAULT 'UNKNOWN'"))
            if "triggered_by_user_id" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN triggered_by_user_id INTEGER"))
            if "results_count" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN results_count INTEGER NOT NULL DEFAULT 0"))
            if "message" not in sync_log_columns:
                conn.execute(text("ALTER TABLE sync_logs ADD COLUMN message TEXT"))
            if "attempt_timestamp" not in sync_log_columns:
                if "started_at" in sync_log_columns:
                    conn.execute(text("ALTER TABLE sync_logs ADD COLUMN attempt_timestamp TIMESTAMP"))
                    conn.execute(text("UPDATE sync_logs SET attempt_timestamp = started_at WHERE attempt_timestamp IS NULL"))
                else:
                    conn.execute(text("ALTER TABLE sync_logs ADD COLUMN attempt_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.execute(
                text(
                    "UPDATE sync_logs SET attempt_timestamp = started_at "
                    "WHERE attempt_timestamp IS NULL AND started_at IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE sync_logs SET started_at = attempt_timestamp "
                    "WHERE started_at IS NULL AND attempt_timestamp IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "UPDATE sync_logs SET results_count = COALESCE(leads_created, 0) + COALESCE(leads_skipped, 0) "
                    "WHERE results_count = 0 AND (COALESCE(leads_created, 0) + COALESCE(leads_skipped, 0)) > 0"
                )
            )
            conn.execute(
                text(
                    "UPDATE sync_logs SET status = UPPER(status) "
                    "WHERE status IN ('success', 'partial', 'failed', 'running')"
                )
            )
            conn.execute(text("UPDATE sync_logs SET status = 'WARNING' WHERE status = 'PARTIAL'"))

    snap.refresh()
    if snap.has_table("leads"):
        lead_columns = snap.column_names("leads")
        with engine.begin() as conn:
            if "admission_stage" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN admission_stage VARCHAR(50)"))
            if "admission_stage_entered_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN admission_stage_entered_at TIMESTAMP"))
            if "documents_submitted_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN documents_submitted_at TIMESTAMP"))
            if "source" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN source VARCHAR(50)"))
            if "meta_leadgen_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_leadgen_id VARCHAR(100)"))
            if "meta_campaign_name" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_campaign_name VARCHAR(255)"))
            if "meta_form_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_form_id VARCHAR(100)"))
            if "meta_ad_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN meta_ad_id VARCHAR(100)"))
            if "additional_data" not in lead_columns:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("ALTER TABLE leads ADD COLUMN additional_data JSONB"))
                else:
                    conn.execute(text("ALTER TABLE leads ADD COLUMN additional_data JSON"))
            if engine.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_leads_meta_leadgen_id "
                        "ON leads (meta_leadgen_id) WHERE meta_leadgen_id IS NOT NULL"
                    )
                )
                conn.execute(text("ALTER TYPE leadchannel ADD VALUE IF NOT EXISTS 'FACEBOOK'"))

    if snap.has_table("counselling_bookings"):
        booking_columns = snap.column_names("counselling_bookings")
        with engine.begin() as conn:
            if "outcome_key" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN outcome_key VARCHAR(50)"))
            if "wrap_up_notes" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN wrap_up_notes TEXT"))
            if "completed_at" not in booking_columns:
                conn.execute(text("ALTER TABLE counselling_bookings ADD COLUMN completed_at TIMESTAMP"))
            if "intake_assessment" not in booking_columns:
                conn.execute(
                    text("ALTER TABLE counselling_bookings ADD COLUMN intake_assessment JSONB")
                )

    if not snap.has_table("admission_history"):
        from app.models.admission_history import AdmissionHistory

        AdmissionHistory.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("admission_history")

    if not snap.has_table("candidate_tasks"):
        from app.models.candidate_task import CandidateTask

        CandidateTask.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("candidate_tasks")

    if not snap.has_table("conversations"):
        from app.models.conversation import Conversation

        Conversation.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("conversations")

    if not snap.has_table("conversation_participants"):
        from app.models.conversation_participant import ConversationParticipant

        ConversationParticipant.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("conversation_participants")

    if not snap.has_table("internal_messages"):
        from app.models.internal_message import InternalMessage

        InternalMessage.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("internal_messages")

    if not snap.has_table("counselling_notes"):
        from app.models.counselling_note import CounsellingNote

        CounsellingNote.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("counselling_notes")

    if not snap.has_table("candidate_educations"):
        from app.models.candidate_education import CandidateEducation

        CandidateEducation.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("candidate_educations")

    if not snap.has_table("non_academic_activities"):
        from app.models.non_academic_activity import NonAcademicActivity

        NonAcademicActivity.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("non_academic_activities")

    if not snap.has_table("digital_presence_links"):
        from app.models.digital_presence_link import DigitalPresenceLink

        DigitalPresenceLink.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("digital_presence_links")

    if not snap.has_table("research_projects"):
        from app.models.research_project import ResearchProject

        ResearchProject.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("research_projects")

    if not snap.has_table("work_experiences"):
        from app.models.work_experience import WorkExperience, WorkProject

        WorkExperience.__table__.create(bind=engine, checkfirst=True)
        WorkProject.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("work_experiences")
        snap.note_table("work_projects")

    if not snap.has_table("candidate_test_scores"):
        from app.models.candidate_test_score import CandidateTestScore

        CandidateTestScore.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("candidate_test_scores")

    if snap.has_table("candidate_test_scores"):
        score_columns = snap.column_names("candidate_test_scores")
        if "overall_score" not in score_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE candidate_test_scores ADD COLUMN overall_score NUMERIC(6, 2)")
                )

    if not snap.has_table("students_master"):
        from app.models.students_master import StudentsMaster

        StudentsMaster.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("students_master")

    if snap.has_table("students_master"):
        master_columns = snap.column_names("students_master")
        if "aspirations_data" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN aspirations_data JSON"))
        if "gender" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN gender VARCHAR(20)"))
        if "marital_status" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN marital_status VARCHAR(20)"))
        if "spouse_name" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN spouse_name VARCHAR(255)"))
        if "registration_data" not in master_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE students_master ADD COLUMN registration_data JSON"))

    if not snap.has_table("status_definitions"):
        from app.models.status_definition import StatusDefinition

        StatusDefinition.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("status_definitions")

    if not snap.has_table("status_history"):
        from app.models.status_history import StatusHistory

        StatusHistory.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("status_history")

    if not snap.has_table("system_logs"):
        from app.models.system_log import SystemLog

        SystemLog.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("system_logs")

    if snap.has_table("leads"):
        lead_columns = snap.column_names("leads")
        with engine.begin() as conn:
            if "status_definition_id" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN status_definition_id INTEGER"))
            if "status_entered_at" not in lead_columns:
                conn.execute(text("ALTER TABLE leads ADD COLUMN status_entered_at TIMESTAMP"))

    if snap.has_table("internal_messages"):
        message_columns = snap.column_names("internal_messages")
        with engine.begin() as conn:
            if "search_vector" not in message_columns:
                conn.execute(text("ALTER TABLE internal_messages ADD COLUMN search_vector TSVECTOR"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_internal_messages_search_vector "
                    "ON internal_messages USING GIN (search_vector)"
                )
            )
            conn.execute(
                text(
                    "UPDATE internal_messages "
                    "SET search_vector = to_tsvector('english', coalesce(content, '')) "
                    "WHERE search_vector IS NULL"
                )
            )
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_internal_messages_content_trgm "
                    "ON internal_messages USING GIN (content gin_trgm_ops)"
                )
            )
            if "reply_to_message_id" not in message_columns:
                conn.execute(
                    text(
                        "ALTER TABLE internal_messages ADD COLUMN reply_to_message_id INTEGER "
                        "REFERENCES internal_messages(id) ON DELETE SET NULL"
                    )
                )

    if snap.has_table("education_majors"):
        major_columns = snap.column_names("education_majors")
        with engine.begin() as conn:
            if "description" in major_columns and "major_description" not in major_columns:
                conn.execute(
                    text(
                        "ALTER TABLE education_majors "
                        "RENAME COLUMN description TO major_description"
                    )
                )
                major_columns.discard("description")
                major_columns.add("major_description")
            if "major_description" not in major_columns:
                conn.execute(
                    text("ALTER TABLE education_majors ADD COLUMN major_description TEXT")
                )
                major_columns.add("major_description")
            if "sub_majors_key_fields" not in major_columns:
                conn.execute(
                    text(
                        "ALTER TABLE education_majors "
                        "ADD COLUMN sub_majors_key_fields TEXT"
                    )
                )

    if snap.has_table("education_sub_majors"):
        sub_major_columns = snap.column_names("education_sub_majors")
        if "sub_major_description" not in sub_major_columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE education_sub_majors "
                        "ADD COLUMN sub_major_description TEXT"
                    )
                )

    if snap.has_table("programs"):
        program_columns = snap.column_names("programs")
        if "program_url" not in program_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE programs ADD COLUMN program_url VARCHAR(2048)")
                )

    if snap.has_table("scanx_documents"):
        scanx_columns = snap.column_names("scanx_documents")
        if "extracted_fields_json" not in scanx_columns:
            with engine.begin() as conn:
                if engine.dialect.name == "postgresql":
                    conn.execute(
                        text(
                            "ALTER TABLE scanx_documents "
                            "ADD COLUMN extracted_fields_json JSONB"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            "ALTER TABLE scanx_documents "
                            "ADD COLUMN extracted_fields_json JSON"
                        )
                    )

    _ensure_program_major_mapping_sub_uniqueness()

    if not snap.has_table("message_reactions"):
        from app.models.message_reaction import MessageReaction

        MessageReaction.__table__.create(bind=engine, checkfirst=True)
        snap.note_table("message_reactions")


def _ensure_program_major_mapping_sub_uniqueness() -> None:
    """Replace unique(program, major) with unique(program, major, sub) + one NULL sub."""
    inspector = inspect(engine)
    table = "program_education_major_mappings"
    if not inspector.has_table(table):
        return
    with engine.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = :table
                      AND indexname IN (
                          'uq_pem_program_major_sub',
                          'uq_pem_program_major_null_sub'
                      )
                    """
                ),
                {"table": table},
            )
        }
        if existing >= {"uq_pem_program_major_sub", "uq_pem_program_major_null_sub"}:
            return
    old_uq = "uq_program_education_major_mappings_program_major"
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {old_uq}"))
        conn.execute(text(f"DROP INDEX IF EXISTS {old_uq}"))
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_pem_program_major_sub
                ON program_education_major_mappings
                    (program_id, education_major_id, education_sub_major_id)
                WHERE education_sub_major_id IS NOT NULL
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_pem_program_major_null_sub
                ON program_education_major_mappings
                    (program_id, education_major_id)
                WHERE education_sub_major_id IS NULL
                """
            )
        )


INSTITUTION_TYPE_CATALOG = (
    ("PUBLIC_STATE", "Public / State", 1),
    ("PRIVATE", "Private", 2),
    ("COMMUNITY_COLLEGE", "Community College", 3),
    ("TECHNICAL_INSTITUTE", "Technical Institute", 4),
    ("OTHERS", "Others", 5),
)


def _ensure_institution_types_catalog(db_engine=None) -> None:
    """Insert missing institution_types rows; keep Technical Institute visible.

    On conflict, re-activate catalog rows and refresh sort_order. Custom names
    are preserved unless they only differ by surrounding whitespace.
    """
    db_engine = db_engine or engine
    inspector = inspect(db_engine)
    if not inspector.has_table("institutions"):
        return
    if not inspector.has_table("institution_types"):
        from app.models.academia_institution import InstitutionType

        InstitutionType.__table__.create(bind=db_engine, checkfirst=True)
        inspector = inspect(db_engine)

    inst_columns = {column["name"] for column in inspector.get_columns("institutions")}
    if "institution_type_id" not in inst_columns:
        return

    with db_engine.begin() as conn:
        for code, name, sort_order in INSTITUTION_TYPE_CATALOG:
            conn.execute(
                text(
                    """
                    INSERT INTO institution_types (code, name, is_active, sort_order)
                    VALUES (:code, :name, true, :sort_order)
                    ON CONFLICT (code) DO UPDATE SET
                        is_active = true,
                        sort_order = EXCLUDED.sort_order,
                        name = CASE
                            WHEN trim(institution_types.name) = trim(EXCLUDED.name)
                            THEN EXCLUDED.name
                            ELSE institution_types.name
                        END
                    """
                ),
                {"code": code, "name": name, "sort_order": sort_order},
            )


def migrate_audit_logs_schema() -> None:
    """Bring audit_logs in line with the current AuditLog model (idempotent)."""
    from app.models.audit_log import AuditLog

    inspector = inspect(engine)
    if not inspector.has_table("audit_logs"):
        AuditLog.__table__.create(bind=engine, checkfirst=True)
        return

    audit_columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    with engine.begin() as conn:
        if "action" in audit_columns and "action_type" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs RENAME COLUMN action TO action_type"))
            audit_columns.remove("action")
            audit_columns.add("action_type")
        if "resource" in audit_columns and "target_resource" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs RENAME COLUMN resource TO target_resource"))
            audit_columns.remove("resource")
            audit_columns.add("target_resource")
        if "details" not in audit_columns:
            if engine.dialect.name == "postgresql":
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN details JSONB"))
            else:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN details JSON"))
            audit_columns.add("details")
            if "detail" in audit_columns and engine.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "UPDATE audit_logs SET details = jsonb_build_object('legacy_detail', detail) "
                        "WHERE detail IS NOT NULL AND detail <> '' AND details IS NULL"
                    )
                )
        if "session_id" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN session_id VARCHAR(128)"))
        if "sync_mode" not in audit_columns:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN sync_mode VARCHAR(20)"))


def _release_scanx_slot(db: Session | None) -> None:
    if db is None:
        return
    try:
        held = bool(db.info.pop("_scanx_slot", False))
        long_gate = bool(db.info.pop("_scanx_long_gate", False))
    except Exception:
        held = False
        long_gate = False
    if long_gate:
        _scanx_long_connect_gate.active = False
    if held:
        try:
            _SCANX_DB_SLOTS.release()
        except ValueError:
            pass


def safe_close_session(db: Session) -> None:
    """Close a session without surfacing rollback errors on dead connections.

    ``Session.close()`` sends ROLLBACK. When the SSH tunnel has already dropped
    the socket, that ROLLBACK raises OperationalError and Starlette logs a full
    traceback on the way out of middleware. Invalidate the connection instead.
    """
    try:
        try:
            db.close()
            return
        except Exception:
            pass
        try:
            db.invalidate()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass
    finally:
        _release_scanx_slot(db)


def ensure_db_connection(db: Session) -> None:
    """Ping and recover pooled connections after long idle periods (e.g. Meta sync)."""
    try:
        db.execute(text("SELECT 1"))
        return
    except (OperationalError, DBAPIError) as exc:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.invalidate()
        except Exception:
            pass
        if _IS_SSH_TUNNEL_DB and should_dispose_pool_for_error(exc):
            dispose_db_pool(reason="ensure_db_connection ping failed")
        db.execute(text("SELECT 1"))


def get_db():
    """Yield a DB session. pool_pre_ping recovers dead sockets on checkout."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        safe_close_session(db)
