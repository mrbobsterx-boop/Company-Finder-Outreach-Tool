"""Abstract mail-sending interface.

SMTP against a free-tier transactional provider (e.g. Brevo, ~300/day free)
is the default. Swapping in a paid cold-outreach platform (Instantly,
Smartlead, ...) later means writing one more MailProvider, not touching the
compliance/CLI layers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class SendResult:
    status: str  # "sent" | "failed"
    error: Optional[str] = None


class MailProvider(ABC):
    @abstractmethod
    def send(self, to_email: str, subject: str, html_body: str) -> SendResult:
        raise NotImplementedError
