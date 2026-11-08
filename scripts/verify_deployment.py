#!/usr/bin/env python3
"""Check a hosted EduShield environment from the outside. Nothing is changed and no secret is printed.

    BASE_URL=https://app.example.edu \\
    VERIFY_ADMIN_EMAIL=... VERIFY_ADMIN_PASSWORD=... \\
    VERIFY_STAFF_EMAIL=... VERIFY_STAFF_PASSWORD=... \\
    VERIFY_STUDENT_EMAIL=... VERIFY_STUDENT_PASSWORD=... \\
    backend/.venv/bin/python scripts/verify_deployment.py

Pass --allow-http only to rehearse against a local stack. Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from http.cookies import SimpleCookie

import httpx

SESSION_COOKIE = "edushield_session"
CLIENT_HEADER = {"X-EduShield-Client": "verify-deployment"}


@dataclass
class Result:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


class Verifier:
    def __init__(self, base_url: str, allow_http: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.allow_http = allow_http
        self.http = httpx.Client(base_url=self.base_url, timeout=20, follow_redirects=False)
        self.results: list[Result] = []

    def check(self, name: str, passed: bool, detail: str = "") -> bool:
        self.results.append(Result(name, "PASS" if passed else "FAIL", detail))
        return passed

    def skip(self, name: str, detail: str) -> None:
        self.results.append(Result(name, "SKIP", detail))

    def credentials(self, role: str) -> tuple[str, str] | None:
        email, password = os.environ.get(f"VERIFY_{role}_EMAIL"), os.environ.get(f"VERIFY_{role}_PASSWORD")
        return (email, password) if email and password else None

    def bearer(self, role: str) -> dict[str, str] | None:
        creds = self.credentials(role)
        if creds is None:
            self.skip(f"{role.lower()} sign-in", f"VERIFY_{role}_EMAIL and VERIFY_{role}_PASSWORD are not set")
            return None
        response = self.http.post("/api/v1/auth/token", data={"username": creds[0], "password": creds[1]})
        if not self.check(f"{role.lower()} sign-in", response.status_code == 200, f"HTTP {response.status_code}"):
            return None
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def transport(self) -> None:
        secure = self.base_url.startswith("https://")
        if secure:
            self.check("web client uses HTTPS", True)
            plain = httpx.get(self.base_url.replace("https://", "http://", 1), timeout=20, follow_redirects=False)
            self.check(
                "HTTP redirects to HTTPS",
                plain.status_code in (301, 302, 307, 308) and plain.headers.get("location", "").startswith("https://"),
                f"HTTP {plain.status_code}",
            )
        elif self.allow_http:
            self.skip("web client uses HTTPS", "local rehearsal with --allow-http")
        else:
            self.check("web client uses HTTPS", False, "BASE_URL is not https")

    def frontend(self) -> None:
        response = self.http.get("/")
        self.check("web client responds", response.status_code == 200 and 'id="root"' in response.text)
        self.check("content security policy set", "content-security-policy" in response.headers)
        self.check("HSTS set", "strict-transport-security" in response.headers)
        deep_link = self.http.get("/student/applications")
        self.check("client-side routes load", deep_link.status_code == 200 and 'id="root"' in deep_link.text)

    def api(self) -> None:
        health = self.http.get("/api/health")
        self.check("API health endpoint", health.status_code == 200 and health.json().get("status") == "ok")
        ready = self.http.get("/api/ready")
        body = ready.json() if ready.status_code == 200 else {}
        self.check("database reachable", body.get("database") == "ok", f"HTTP {ready.status_code}")
        self.check("background queue configured", body.get("jobs_backend") == "celery", str(body.get("jobs_backend")))
        self.check("API docs hidden", self.http.get("/api/docs").status_code == 404)
        unknown = self.http.get("/api/v1/does-not-exist")
        self.check("unknown API paths return JSON", "application/json" in unknown.headers.get("content-type", ""))

    def browser_controls(self) -> None:
        origin = "https://not-this-application.example"
        preflight = self.http.options(
            "/api/v1/auth/login",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        self.check("foreign origin refused by CORS", "access-control-allow-origin" not in preflight.headers)
        forged = self.http.post("/api/v1/auth/logout", cookies={SESSION_COOKIE: "forged"})
        self.check("CSRF header enforced", forged.status_code == 403, f"HTTP {forged.status_code}")

    def session_cookie(self) -> None:
        creds = self.credentials("ADMIN")
        if creds is None:
            self.skip("session cookie attributes", "administrator credentials are not set")
            return
        response = self.http.post(
            "/api/v1/auth/login", json={"email": creds[0], "password": creds[1]}, headers=CLIENT_HEADER
        )
        header = response.headers.get("set-cookie", "")
        cookie = SimpleCookie()
        cookie.load(header)
        morsel = cookie.get(SESSION_COOKIE)
        if not self.check("browser sign-in sets a session", response.status_code == 200 and morsel is not None):
            return
        self.check("cookie is HttpOnly", bool(morsel["httponly"]))
        self.check("cookie is SameSite=Strict", morsel["samesite"].lower() == "strict")
        if self.allow_http and not self.base_url.startswith("https://"):
            self.skip("cookie is Secure", "local rehearsal with --allow-http")
        else:
            self.check("cookie is Secure", bool(morsel["secure"]))
        self.http.cookies.clear()

    def infrastructure(self, admin: dict[str, str]) -> None:
        response = self.http.get("/api/v1/operations/overview", headers=admin)
        if not self.check("operations overview", response.status_code == 200, f"HTTP {response.status_code}"):
            return
        health = {item["key"]: item for item in response.json()["health"]}
        for key, label in (
            ("database", "database connection"),
            ("migrations", "migrations current"),
            ("jobs", "Redis and worker running"),
            ("scheduler", "scheduler running"),
            ("rate_limit", "shared rate limiting"),
            ("storage", "evidence storage"),
            ("scanner", "malware scanner"),
            ("email", "email delivery configured"),
        ):
            item = health.get(key)
            if item is None:
                self.skip(label, "not reported by this version")
            else:
                self.check(label, item["status"] == "ok", f"{item['status']}: {item['detail']}")

    def roles(self, staff: dict[str, str] | None, student: dict[str, str] | None) -> None:
        if staff:
            queue = self.http.get("/api/v1/applications", headers=staff)
            self.check("staff can read applications", queue.status_code == 200)
            self.check(
                "staff refused the student dashboard",
                self.http.get("/api/v1/student-portal/dashboard", headers=staff).status_code == 403,
            )
        if student:
            self.check(
                "student can read their dashboard",
                self.http.get("/api/v1/student-portal/dashboard", headers=student).status_code == 200,
            )
            refused = self.http.get("/api/v1/applications", headers=student)
            self.check("student refused staff records", refused.status_code == 403)

    def login_rate_limit(self) -> None:
        """Sends failed sign-ins for an address that does not exist, forging every common client-address header.

        45 attempts exceed two fixed windows of 20, so a window boundary cannot hide a working limit.
        """
        codes = [
            self.http.post(
                "/api/v1/auth/login",
                json={"email": "verify.rate.limit@northbridge.example", "password": "not-a-real-password"},
                headers={
                    **CLIENT_HEADER,
                    "X-Forwarded-For": f"203.0.113.{attempt}",
                    "X-Real-IP": f"203.0.113.{attempt}",
                    "True-Client-IP": f"203.0.113.{attempt}",
                },
            ).status_code
            for attempt in range(1, 46)
        ]
        limited = codes.count(429)
        self.check("sign-in limit holds against a spoofed client address", limited > 0, f"{limited} of 45 limited")

    def run(self, check_rate_limit: bool = False) -> int:
        self.transport()
        self.frontend()
        self.api()
        self.browser_controls()
        self.session_cookie()
        admin, staff, student = self.bearer("ADMIN"), self.bearer("STAFF"), self.bearer("STUDENT")
        if admin:
            self.infrastructure(admin)
        self.roles(staff, student)
        if check_rate_limit:
            self.login_rate_limit()
        for result in self.results:
            print(f"{result.status:5} {result.name}{f' ({result.detail})' if result.detail else ''}")
        failed = sum(result.status == "FAIL" for result in self.results)
        skipped = sum(result.status == "SKIP" for result in self.results)
        print(f"\n{len(self.results) - failed - skipped} passed, {failed} failed, {skipped} skipped")
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-http", action="store_true", help="rehearse against a local stack without TLS")
    parser.add_argument("--check-rate-limit", action="store_true", help="also send 45 failed sign-ins")
    args = parser.parse_args()
    base_url = os.environ.get("BASE_URL")
    if not base_url:
        print("Set BASE_URL to the deployed application's address.", file=sys.stderr)
        return 2
    return Verifier(base_url, args.allow_http).run(args.check_rate_limit)


if __name__ == "__main__":
    raise SystemExit(main())
