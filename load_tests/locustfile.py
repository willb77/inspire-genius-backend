from __future__ import annotations

"""
Locust load testing suite for Inspire Genius Backend.

Covers critical user flows: auth, dashboard, feedback, analytics,
goals, training, costs, and reports.

Run:
    locust -f load_tests/locustfile.py --headless -u 100 -r 10 -t 60s
"""

import json
import random
import uuid

from locust import HttpUser, between, tag, task


class InspireGeniusUser(HttpUser):
    """Simulates a typical Inspire Genius platform user."""

    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self) -> None:
        """Authenticate and store the access token for subsequent requests."""
        resp = self.client.post(
            "/v1/login",
            json={
                "email": "loadtest@example.com",
                "password": "TestPass123!",
            },
            name="/v1/login [on_start]",
        )
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            self.token = data.get("access_token", "test-token")
        else:
            self.token = "test-token"
        self.headers = {"access-token": self.token}

    # ── Auth ────────────────────────────────────────────────────────────

    @tag("critical", "auth")
    @task(3)
    def login(self) -> None:
        """POST /v1/login — authenticate a user."""
        with self.client.post(
            "/v1/login",
            json={
                "email": "loadtest@example.com",
                "password": "TestPass123!",
            },
            name="/v1/login",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Dashboard ───────────────────────────────────────────────────────

    @tag("critical", "dashboard")
    @task(5)
    def get_dashboard(self) -> None:
        """GET /v1/user/dashboard/stats — main dashboard statistics."""
        with self.client.get(
            "/v1/user/dashboard/stats",
            headers=self.headers,
            name="/v1/user/dashboard/stats",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    @tag("critical", "dashboard")
    @task(3)
    def get_activity(self) -> None:
        """GET /v1/user/dashboard/activity — recent activity feed."""
        with self.client.get(
            "/v1/user/dashboard/activity",
            headers=self.headers,
            name="/v1/user/dashboard/activity",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Feedback ────────────────────────────────────────────────────────

    @tag("feedback")
    @task(2)
    def submit_feedback(self) -> None:
        """POST /v1/feedback — submit user feedback."""
        payload = {
            "agent_id": str(uuid.uuid4()),
            "feedback_type": random.choice(["thumbs_up", "thumbs_down", "text"]),
            "message": "Load test feedback message",
            "rating": random.randint(1, 5),
        }
        with self.client.post(
            "/v1/feedback",
            json=payload,
            headers=self.headers,
            name="/v1/feedback [POST]",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 201, 401, 403, 422):
                resp.failure(f"Unexpected status {resp.status_code}")

    @tag("feedback")
    @task(2)
    def list_feedback(self) -> None:
        """GET /v1/feedback — list user feedback."""
        with self.client.get(
            "/v1/feedback",
            headers=self.headers,
            name="/v1/feedback [GET]",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Analytics ───────────────────────────────────────────────────────

    @tag("analytics")
    @task(2)
    def get_analytics(self) -> None:
        """GET /v1/analytics/user — user-level analytics."""
        with self.client.get(
            "/v1/analytics/user",
            headers=self.headers,
            name="/v1/analytics/user",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Goals ───────────────────────────────────────────────────────────

    @tag("goals")
    @task(2)
    def get_goals(self) -> None:
        """GET /v1/user/goals — user goals."""
        with self.client.get(
            "/v1/user/goals",
            headers=self.headers,
            name="/v1/user/goals",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Training ────────────────────────────────────────────────────────

    @tag("training")
    @task(1)
    def get_training(self) -> None:
        """GET /v1/user/training — training resources."""
        with self.client.get(
            "/v1/user/training",
            headers=self.headers,
            name="/v1/user/training",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Costs ───────────────────────────────────────────────────────────

    @tag("costs")
    @task(1)
    def get_costs(self) -> None:
        """GET /v1/costs/dashboard?scope=user — cost dashboard."""
        with self.client.get(
            "/v1/costs/dashboard",
            params={"scope": "user"},
            headers=self.headers,
            name="/v1/costs/dashboard?scope=user",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")

    # ── Reports ─────────────────────────────────────────────────────────

    @tag("reports")
    @task(1)
    def list_reports(self) -> None:
        """GET /v1/reports — list generated reports."""
        with self.client.get(
            "/v1/reports",
            headers=self.headers,
            name="/v1/reports",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 403):
                resp.failure(f"Unexpected status {resp.status_code}")
