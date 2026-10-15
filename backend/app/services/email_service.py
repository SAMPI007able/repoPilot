import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailSettings:
    host: str | None
    port: int
    username: str | None
    password: str | None
    sender: str | None
    use_ssl: bool
    use_starttls: bool
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "EmailSettings":
        use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
        return cls(
            host=os.getenv("SMTP_HOST") or None,
            port=int(os.getenv("SMTP_PORT") or ("465" if use_ssl else "587")),
            username=os.getenv("SMTP_USERNAME") or None,
            password=os.getenv("SMTP_PASSWORD") or None,
            sender=os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME") or None,
            use_ssl=use_ssl,
            use_starttls=not use_ssl and os.getenv("SMTP_STARTTLS", "true").lower() == "true",
            timeout_seconds=int(os.getenv("SMTP_TIMEOUT_SECONDS", "15")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.host and self.sender)


class EmailService:
    """Sends transactional email over SMTP. Without SMTP settings, sends are logged and skipped."""

    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return self.settings.configured

    def send(self, recipients: list[str], subject: str, html: str, text: str) -> bool:
        recipients = sorted({address.strip() for address in recipients if address and address.strip()})
        if not recipients:
            return False
        if not self.enabled:
            logger.warning("SMTP is not configured; skipped email %r to %d recipient(s).", subject, len(recipients))
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.sender
        message["To"] = self.settings.sender if len(recipients) > 1 else recipients[0]
        message["Message-ID"] = make_msgid()
        message.set_content(text)
        message.add_alternative(html, subtype="html")

        context = ssl.create_default_context()
        smtp_class = smtplib.SMTP_SSL if self.settings.use_ssl else smtplib.SMTP
        kwargs = {"context": context} if self.settings.use_ssl else {}
        with smtp_class(self.settings.host, self.settings.port, timeout=self.settings.timeout_seconds, **kwargs) as client:
            if self.settings.use_starttls:
                client.starttls(context=context)
            if self.settings.username and self.settings.password:
                client.login(self.settings.username, self.settings.password)
            # Multiple recipients are delivered as Bcc so admins never see each other's addresses.
            client.send_message(message, to_addrs=recipients)
        return True
