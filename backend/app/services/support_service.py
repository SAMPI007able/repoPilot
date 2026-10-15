import html
import logging
import os
import re
import uuid
from collections.abc import Callable
from urllib.parse import urlsplit

import nh3

from app.models.support_models import (
    SUPPORT_CATEGORY_LABELS,
    SUPPORT_STATUS_LABELS,
    AdminSupportTicket,
    SupportTicket,
    SupportTicketCreateRequest,
    SupportTicketStatus,
)
from app.persistence.artifact_store import ArtifactStore
from app.persistence.support_persistence_service import SupportPersistenceService
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ATTACHMENT_PATH_PATTERN = re.compile(r"^/support/uploads/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "sub", "sup", "a", "ul", "ol", "li",
    "blockquote", "code", "pre", "h2", "h3", "h4", "figure", "figcaption", "img", "hr",
    "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "code": {"class"},
    "figure": {"class"},
    "ol": {"start"},
    "th": {"colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
}


class SupportValidationError(ValueError):
    pass


def detect_image_type(contents: bytes) -> str | None:
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contents.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "image/webp"
    return None


class SupportService:
    def __init__(
        self,
        persistence: SupportPersistenceService,
        artifact_store: ArtifactStore,
        email_service: EmailService,
        *,
        frontend_url: str | None = None,
        public_api_url: str | None = None,
        failure_logger: Callable[[str, str], None] | None = None,
    ) -> None:
        self.persistence = persistence
        self.artifact_store = artifact_store
        self.email_service = email_service
        self.frontend_url = (frontend_url or os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")).rstrip("/")
        configured_api_url = public_api_url or os.getenv("API_PUBLIC_URL") or os.getenv("OAUTH_CALLBACK_BASE_URL")
        self.public_api_url = configured_api_url.rstrip("/") if configured_api_url else None
        self.failure_logger = failure_logger

    # ── Tickets ──────────────────────────────────────────────────────────────
    def create_ticket(self, user_id: str, request: SupportTicketCreateRequest) -> AdminSupportTicket:
        subject = " ".join(request.subject.split())
        if len(subject) < 3:
            raise SupportValidationError("Add a short subject for your request.")
        description = self.sanitize_html(request.description_html)
        if not self._has_content(description):
            raise SupportValidationError("Describe the problem before submitting.")
        return self.persistence.create(user_id, request.category, subject, description)

    def list_for_user(self, user_id: str) -> list[SupportTicket]:
        return self.persistence.list_for_user(user_id)

    def list_all(self, status: SupportTicketStatus | None = None) -> list[AdminSupportTicket]:
        return self.persistence.list_all(status)

    def update_status(self, ticket_id: str, status: SupportTicketStatus, actor_user_id: str) -> AdminSupportTicket:
        return self.persistence.update_status(ticket_id, status, actor_user_id)

    # ── Attachments ──────────────────────────────────────────────────────────
    def store_image(self, user_id: str, contents: bytes, base_url: str) -> str:
        if not contents:
            raise SupportValidationError("The uploaded file is empty.")
        if len(contents) > MAX_ATTACHMENT_BYTES:
            raise SupportValidationError("Images must be 5 MB or smaller.")
        content_type = detect_image_type(contents)
        if content_type is None:
            raise SupportValidationError("Only PNG, JPEG, GIF, and WebP images can be uploaded.")
        attachment_id = str(uuid.uuid4())
        storage_key = f"support/{attachment_id}"
        self.artifact_store.put(storage_key, contents, content_type)
        self.persistence.create_attachment(user_id, storage_key, content_type, len(contents), attachment_id)
        return f"{(self.public_api_url or base_url).rstrip('/')}/support/uploads/{attachment_id}"

    def load_image(self, attachment_id: str) -> tuple[bytes, str]:
        storage_key, content_type = self.persistence.attachment(attachment_id)
        return self.artifact_store.get(storage_key), content_type

    # ── Sanitization ─────────────────────────────────────────────────────────
    def sanitize_html(self, value: str) -> str:
        return nh3.clean(
            value,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            url_schemes={"http", "https", "mailto"},
            link_rel="noopener noreferrer nofollow",
            attribute_filter=self._filter_attribute,
        ).strip()

    def _filter_attribute(self, tag: str, attribute: str, value: str) -> str | None:
        if tag == "img" and attribute == "src":
            return value if self._is_attachment_url(value) else None
        return value

    def _is_attachment_url(self, value: str) -> bool:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not ATTACHMENT_PATH_PATTERN.match(parts.path):
            return False
        if self.public_api_url is None:
            return True
        return value.startswith(f"{self.public_api_url}/support/uploads/")

    @staticmethod
    def _has_content(description: str) -> bool:
        text = nh3.clean(description, tags=set()).replace("&nbsp;", " ").strip()
        return bool(text) or "<img" in description

    # ── Notifications ────────────────────────────────────────────────────────
    def notify_admins_of_new_ticket(self, ticket: AdminSupportTicket) -> None:
        recipients = self.persistence.admin_emails()
        category = SUPPORT_CATEGORY_LABELS[ticket.category]
        requester = ticket.user_display_name or ticket.user_email
        subject = f"[TestForge Support] {category}: {ticket.subject}"
        details = (
            f"<p><strong>From:</strong> {html.escape(requester)} &lt;{html.escape(ticket.user_email)}&gt;<br>"
            f"<strong>Category:</strong> {html.escape(category)}<br>"
            f"<strong>Ticket:</strong> {html.escape(ticket.id)}</p>"
        )
        body = self._layout(
            f"New support ticket: {ticket.subject}",
            f"{details}<hr>{ticket.description_html}",
            f"{self.frontend_url}/admin#support",
            "Open in admin panel",
        )
        text = (
            f"New support ticket from {requester} <{ticket.user_email}>\n"
            f"Category: {category}\nSubject: {ticket.subject}\nTicket: {ticket.id}\n\n"
            f"{nh3.clean(ticket.description_html, tags=set())}\n\n"
            f"Manage tickets: {self.frontend_url}/admin#support\n"
        )
        self._deliver(recipients, subject, body, text, ticket.id)

    def notify_requester_of_status(self, ticket: AdminSupportTicket) -> None:
        status = SUPPORT_STATUS_LABELS[ticket.status]
        subject = f"[TestForge Support] Your ticket is {status}: {ticket.subject}"
        message = {
            SupportTicketStatus.IN_PROGRESS: "Our team has started working on your support request.",
            SupportTicketStatus.COMPLETED: "Your support request has been marked as completed.",
        }.get(ticket.status, f"Your support request is now {status}.")
        body = self._layout(
            f"Ticket {status}",
            f"<p>{html.escape(message)}</p>"
            f"<p><strong>Subject:</strong> {html.escape(ticket.subject)}<br>"
            f"<strong>Category:</strong> {html.escape(SUPPORT_CATEGORY_LABELS[ticket.category])}<br>"
            f"<strong>Status:</strong> {html.escape(status)}</p>"
            f"<hr><p style=\"color:#6b7280\">Your original message:</p>{ticket.description_html}",
            f"{self.frontend_url}/support",
            "View my support tickets",
        )
        text = (
            f"{message}\n\nSubject: {ticket.subject}\nStatus: {status}\n\n"
            f"View your tickets: {self.frontend_url}/support\n"
        )
        self._deliver([ticket.user_email], subject, body, text, ticket.id)

    def _deliver(self, recipients: list[str], subject: str, body: str, text: str, ticket_id: str) -> None:
        try:
            self.email_service.send(recipients, subject, body, text)
        except Exception as exc:  # Email must never break ticket workflows.
            logger.exception("Support email for ticket %s failed.", ticket_id)
            if self.failure_logger:
                try:
                    self.failure_logger(f"Support email for ticket {ticket_id} failed: {exc}", ticket_id)
                except Exception:
                    pass

    @staticmethod
    def _layout(heading: str, content: str, action_url: str, action_label: str) -> str:
        return (
            "<!doctype html><html><body style=\"margin:0;padding:24px;background:#f3f4f6;"
            "font-family:Inter,Segoe UI,Arial,sans-serif;color:#111827\">"
            "<div style=\"max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden\">"
            "<div style=\"padding:18px 24px;background:#0b0d12;color:#f7f8fa;font-weight:700\">TestForge Support</div>"
            f"<div style=\"padding:24px\"><h2 style=\"margin:0 0 16px;font-size:20px\">{html.escape(heading)}</h2>"
            f"{content}"
            f"<p style=\"margin-top:24px\"><a href=\"{html.escape(action_url)}\" style=\"display:inline-block;"
            "padding:10px 16px;border-radius:8px;background:#22d3ee;color:#06111b;text-decoration:none;font-weight:600\">"
            f"{html.escape(action_label)}</a></p></div></div></body></html>"
        )
