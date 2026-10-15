"""Server-owned daily-feed collection, independent of public write permissions."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
import sqlite3
import threading
import time

from .feed import ERROR_MESSAGES, FeedError, refresh_feed

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedSchedule:
    enabled: bool
    state: str = "Maharashtra"
    commodity: str = "Tomato"
    market: str = ""
    interval: int = 21600
    max_pages: int = 3

    @classmethod
    def from_environment(cls, environment):
        enabled = os.getenv("HARVESTSHIELD_AUTO_REFRESH", "true" if environment == "production" else "false").lower()
        if enabled not in ("true", "false"):
            raise ValueError("HARVESTSHIELD_AUTO_REFRESH must be true or false.")
        try:
            interval = int(os.getenv("HARVESTSHIELD_REFRESH_SECONDS", "21600"))
            pages = int(os.getenv("HARVESTSHIELD_FEED_MAX_PAGES", "3"))
        except ValueError:
            raise ValueError("Feed interval and page limit must be integers.") from None
        if not 900 <= interval <= 604800 or not 1 <= pages <= 10:
            raise ValueError("Refresh interval must be 900–604800 seconds; feed page limit must be 1–10.")
        filters = [os.getenv(name, default).strip() for name, default in (
            ("HARVESTSHIELD_FEED_STATE", "Maharashtra"),
            ("HARVESTSHIELD_FEED_COMMODITY", "Tomato"), ("HARVESTSHIELD_FEED_MARKET", ""))]
        if not all(0 < len(value) <= 150 for value in filters[:2]) or len(filters[2]) > 150:
            raise ValueError("Supply valid feed state, commodity and optional market filters (max 150 characters).")
        return cls(enabled == "true", *filters, interval, pages)


def timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


class FeedCollector:
    def __init__(self, store, schedule, feed_lock):
        self.store, self.schedule, self.feed_lock = store, schedule, feed_lock
        self.shutdown = threading.Event()
        self.thread = None
        # Status and the retry deadline survive restarts on the same /state volume.
        with store.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS feed_schedule (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")

    def _load(self, conn):
        row = conn.execute("SELECT payload FROM feed_schedule WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {}

    def _save(self, conn, status):
        conn.execute("INSERT OR REPLACE INTO feed_schedule(id,payload) VALUES (1,?)", (json.dumps(status),))

    def _identity(self):
        s = self.schedule
        return [s.state, s.commodity, s.market, s.max_pages, s.interval, "state-keyword-diagnostics-v2"]

    def status(self):
        with self.store.connection() as conn:
            status = self._load(conn)
        matching = status.get("configuration") == self._identity()
        if not matching:
            status = {}
        state = status.get("state", "waiting")
        if not self.schedule.enabled:
            state = "disabled"
        elif not os.getenv("DATA_GOV_API_KEY", "").strip():
            state = "missing_key"
        return {"enabled": self.schedule.enabled, "state": state,
            "filters": dict(zip(("state", "commodity", "market"), self._identity()[:3])),
            "interval_seconds": self.schedule.interval,
            "last_attempt": timestamp(status.get("last_attempt")),
            "last_success": timestamp(status.get("last_success")),
            "next_attempt": timestamp(status.get("next_attempt")) if state not in ("disabled", "missing_key") else None,
            "inserted": status.get("inserted", 0), "repeated": status.get("repeated", 0),
            "page_limit_reached": status.get("page_limit_reached", False),
            "message": status.get("message", ""), "failures": status.get("failures", 0),
            "error_code": status.get("error_code"), "upstream_status": status.get("upstream_status")}

    def run_once(self, now=None):
        if not self.schedule.enabled or not os.getenv("DATA_GOV_API_KEY", "").strip():
            return False
        if not self.feed_lock.acquire(blocking=False):
            return False
        now = time.time() if now is None else now
        try:
            with self.store.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                status = self._load(conn)
                if status.get("configuration") != self._identity():
                    status = {"configuration": self._identity()}
                if now < status.get("next_attempt", 0):
                    return False
                status.update(state="fetching", last_attempt=now, next_attempt=now + 900)
                self._save(conn, status)
            try:
                result = refresh_feed(self.store, self.schedule.state, self.schedule.commodity,
                                      self.schedule.market, self.schedule.max_pages)
            except Exception as exc:
                # Never log exception text/tracebacks: provider URLs can contain keys.
                failures = status.get("failures", 0) + 1
                delay = min(self.schedule.interval, 900 * 2 ** min(failures - 1, 6))
                code = exc.code if isinstance(exc, FeedError) else "STORAGE" if isinstance(exc, sqlite3.Error) else "INTERNAL"
                upstream = exc.upstream_status if isinstance(exc, FeedError) else None
                status.update(state="error", failures=failures, next_attempt=now + delay,
                    error_code=code, upstream_status=upstream, message=ERROR_MESSAGES[code])
                log.warning("Automatic feed refresh failed [%s, HTTP=%s]; retry scheduled in %s seconds.", code, upstream, delay)
            else:
                status.update(state="success", failures=0, last_success=now,
                    error_code=None, upstream_status=None,
                    next_attempt=now + self.schedule.interval, inserted=result["inserted"],
                    repeated=result["repeated"], page_limit_reached=result.get("page_limit_reached", False),
                    message="Reported daily prices imported. This is not historical backfill or a continuous auction feed.")
                log.info("Automatic feed refresh completed: %s inserted, %s repeated.", result["inserted"], result["repeated"])
            with self.store.connection() as conn:
                self._save(conn, status)
            return True
        finally:
            self.feed_lock.release()

    def _loop(self):
        while not self.shutdown.is_set():
            try:
                self.run_once()
            except Exception:
                log.error("Automatic collector storage failure; will retry without interrupting public reads.")
            self.shutdown.wait(15)

    def start(self):
        if self.schedule.enabled:
            if not os.getenv("DATA_GOV_API_KEY", "").strip():
                log.warning("Automatic prices enabled, but DATA_GOV_API_KEY is missing; collection is waiting for configuration.")
            self.thread = threading.Thread(target=self._loop, name="harvest-feed", daemon=True)
            self.thread.start()

    def stop(self):
        self.shutdown.set()
        if self.thread:
            self.thread.join(timeout=5)
