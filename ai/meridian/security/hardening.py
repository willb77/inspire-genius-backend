from __future__ import annotations

"""
Production Hardening — security audit, prompt injection protection, PII handling.
"""

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
import re
import uuid


class ThreatLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SecurityScanResult(BaseModel):
    """Result of a security scan on user input."""
    scan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    threat_level: ThreatLevel
    threats_detected: list[str] = Field(default_factory=list)
    sanitized_input: str = ""
    blocked: bool = False


class PIIScanResult(BaseModel):
    """Result of PII detection scan."""
    has_pii: bool = False
    pii_types: list[str] = Field(default_factory=list)
    redacted_text: str = ""


# Prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(previous|above|all)\s+(instructions|prompts|rules)",
    r"you\s+are\s+now\s+(a|an|the)\s+",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"forget\s+(everything|all|your)\s+(you|instructions|training)",
    r"pretend\s+you\s+are",
    r"act\s+as\s+(if|a|an|the)",
    r"override\s+(your|the|all)",
    r"new\s+instructions?\s*:",
    r"disregard\s+(all|your|the|previous)",
]

# PII patterns
PII_PATTERNS = {
    "ssn": r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    "phone": r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b",
    "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
}


class PromptGuard:
    """
    Protects against prompt injection attacks.

    Scans user input for injection patterns and sanitizes
    or blocks malicious inputs.
    """

    def scan(self, user_input: str) -> SecurityScanResult:
        """Scan user input for prompt injection attempts."""
        threats = []
        text_lower = user_input.lower()

        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, text_lower):
                threats.append(f"Injection pattern detected: {pattern[:30]}...")

        if not threats:
            return SecurityScanResult(
                threat_level=ThreatLevel.NONE,
                sanitized_input=user_input,
            )

        threat_level = ThreatLevel.HIGH if len(threats) >= 2 else ThreatLevel.MEDIUM

        return SecurityScanResult(
            threat_level=threat_level,
            threats_detected=threats,
            sanitized_input=self._sanitize(user_input),
            blocked=threat_level == ThreatLevel.HIGH,
        )

    def _sanitize(self, text: str) -> str:
        """Remove potentially dangerous patterns from input."""
        sanitized = text
        for pattern in INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[filtered]", sanitized, flags=re.IGNORECASE)
        return sanitized


class PIIHandler:
    """
    Detects and redacts personally identifiable information.

    Behavioral data (PRISM scores, preferences) is NOT treated as PII —
    it's core to the coaching experience. Actual PII (SSN, CC, etc.) is redacted.
    """

    def scan(self, text: str) -> PIIScanResult:
        """Scan text for PII."""
        pii_types = []
        redacted = text

        for pii_type, pattern in PII_PATTERNS.items():
            if re.search(pattern, text):
                pii_types.append(pii_type)
                redacted = re.sub(pattern, f"[REDACTED_{pii_type.upper()}]", redacted)

        return PIIScanResult(
            has_pii=len(pii_types) > 0,
            pii_types=pii_types,
            redacted_text=redacted,
        )

    def redact(self, text: str) -> str:
        """Redact all PII from text."""
        return self.scan(text).redacted_text


class SecurityAuditor:
    """
    Comprehensive security auditor for the Meridian system.

    Combines prompt injection protection, PII handling, and
    behavioral data access controls.
    """

    def __init__(self) -> None:
        self._prompt_guard = PromptGuard()
        self._pii_handler = PIIHandler()
        self._audit_log: list[dict[str, Any]] = []

    def audit_input(self, user_input: str, user_id: str) -> dict[str, Any]:
        """Full security audit on user input."""
        injection_scan = self._prompt_guard.scan(user_input)
        pii_scan = self._pii_handler.scan(user_input)

        result = {
            "user_id": user_id,
            "injection": injection_scan.model_dump(),
            "pii": pii_scan.model_dump(),
            "safe_input": injection_scan.sanitized_input if not injection_scan.blocked else "",
            "blocked": injection_scan.blocked,
        }

        self._audit_log.append(result)

        if injection_scan.blocked:
            logger.warning(f"SecurityAuditor: blocked input from user {user_id}")
        if pii_scan.has_pii:
            logger.info(f"SecurityAuditor: PII detected and redacted for user {user_id}")

        return result

    def audit_output(self, output: str, agent_id: str) -> dict[str, Any]:
        """Audit agent output for PII leakage."""
        pii_scan = self._pii_handler.scan(output)
        return {
            "agent_id": agent_id,
            "pii": pii_scan.model_dump(),
            "safe_output": pii_scan.redacted_text,
        }

    def get_audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._audit_log[-limit:]

    @property
    def prompt_guard(self) -> PromptGuard:
        return self._prompt_guard

    @property
    def pii_handler(self) -> PIIHandler:
        return self._pii_handler
