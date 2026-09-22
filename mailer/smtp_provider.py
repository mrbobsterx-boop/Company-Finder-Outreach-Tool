"""SMTP mail provider, defaults tuned for Brevo's free transactional tier."""
from __future__ import annotations

import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from mailer.base import MailProvider, SendResult

logger = logging.getLogger(__name__)


class SMTPMailProvider(MailProvider):
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str,
        throttle_seconds: float = 8.0,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        self.throttle_seconds = throttle_seconds
        self._last_send_time: float | None = None

    def _throttle(self) -> None:
        """Space sends out so the sending domain doesn't look like spam."""
        if self._last_send_time is not None:
            elapsed = time.monotonic() - self._last_send_time
            remaining = self.throttle_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_send_time = time.monotonic()

    def send(self, to_email: str, subject: str, html_body: str) -> SendResult:
        self._throttle()

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = to_email
        message.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.from_email, [to_email], message.as_string())
            return SendResult(status="sent")
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("Failed to send to %s: %s", to_email, exc)
            return SendResult(status="failed", error=str(exc))
