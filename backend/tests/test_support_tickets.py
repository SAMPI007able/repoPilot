import os
import tempfile
import unittest

from app.models.support_models import SupportCategory, SupportTicketCreateRequest, SupportTicketStatus
from app.persistence.artifact_store import LocalArtifactStore
from app.persistence.database import Database
from app.persistence.models import UserRow
from app.persistence.support_persistence_service import (
    SupportPersistenceService,
    SupportTicketNotFoundError,
    SupportTicketTransitionError,
)
from app.services.support_service import SupportService, SupportValidationError

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class RecordingEmailService:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[list[str], str, str, str]] = []
        self.fail = fail

    def send(self, recipients, subject, html, text):
        if self.fail:
            raise ConnectionError("SMTP unavailable")
        self.sent.append((sorted(recipients), subject, html, text))
        return True


class SupportTicketTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.artifacts = tempfile.TemporaryDirectory()
        self.database = Database(f"sqlite:///{self.path.replace(os.sep, '/')}")
        self.database.create_schema()
        with self.database.session() as session:
            session.add_all([
                UserRow(id="user-1", primary_email="user@example.test", display_name="Uma User",
                        status="ACTIVE", role="USER", email_verified=True),
                UserRow(id="admin-1", primary_email="admin@example.test", status="ACTIVE",
                        role="ADMIN", email_verified=True),
                UserRow(id="admin-2", primary_email="suspended-admin@example.test", status="SUSPENDED",
                        role="ADMIN", email_verified=True),
            ])
        self.email = RecordingEmailService()
        self.failures: list[str] = []
        self.service = SupportService(
            SupportPersistenceService(self.database),
            LocalArtifactStore(self.artifacts.name),
            self.email,
            frontend_url="https://app.example.test",
            public_api_url="https://api.example.test",
            failure_logger=lambda message, _ticket_id: self.failures.append(message),
        )

    def tearDown(self):
        self.database.close()
        self.artifacts.cleanup()
        os.unlink(self.path)

    def create(self, description="<p>Chat answers are empty.</p>", subject="Chat is broken"):
        return self.service.create_ticket("user-1", SupportTicketCreateRequest(
            category=SupportCategory.CHAT_WITH_CODEBASE, subject=subject, descriptionHtml=description,
        ))

    def test_ticket_is_created_open_and_listed_for_owner_only(self):
        ticket = self.create()

        self.assertEqual(ticket.status, SupportTicketStatus.OPEN)
        self.assertEqual(ticket.user_email, "user@example.test")
        self.assertEqual([item.id for item in self.service.list_for_user("user-1")], [ticket.id])
        self.assertEqual(self.service.list_for_user("admin-1"), [])
        self.assertEqual([item.id for item in self.service.list_all()], [ticket.id])
        self.assertEqual(self.service.list_all(SupportTicketStatus.COMPLETED), [])

    def test_description_html_is_sanitized(self):
        ticket = self.create(
            '<p onclick="steal()">Hi<script>alert(1)</script> <a href="javascript:alert(1)">x</a></p>'
            '<img src="https://evil.example/pixel.png">'
            '<img src="https://api.example.test/support/uploads/0f8fad5b-d9cb-469f-a165-70867728950e">'
        )

        self.assertNotIn("script", ticket.description_html)
        self.assertNotIn("onclick", ticket.description_html)
        self.assertNotIn("javascript:", ticket.description_html)
        self.assertNotIn("evil.example", ticket.description_html)
        self.assertIn("https://api.example.test/support/uploads/0f8fad5b", ticket.description_html)

    def test_empty_description_and_subject_are_rejected(self):
        with self.assertRaises(SupportValidationError):
            self.create(description="<p>&nbsp;</p><script>x</script>")
        with self.assertRaises(SupportValidationError):
            self.create(subject="   a    ")

    def test_status_transitions(self):
        ticket = self.create()

        in_progress = self.service.update_status(ticket.id, SupportTicketStatus.IN_PROGRESS, "admin-1")
        self.assertEqual(in_progress.status, SupportTicketStatus.IN_PROGRESS)
        self.assertIsNotNone(in_progress.in_progress_at)
        with self.assertRaises(SupportTicketTransitionError):
            self.service.update_status(ticket.id, SupportTicketStatus.IN_PROGRESS, "admin-1")

        completed = self.service.update_status(ticket.id, SupportTicketStatus.COMPLETED, "admin-1")
        self.assertEqual(completed.status, SupportTicketStatus.COMPLETED)
        self.assertIsNotNone(completed.completed_at)
        with self.assertRaises(SupportTicketTransitionError):
            self.service.update_status(ticket.id, SupportTicketStatus.IN_PROGRESS, "admin-1")
        with self.assertRaises(SupportTicketNotFoundError):
            self.service.update_status("missing", SupportTicketStatus.COMPLETED, "admin-1")

    def test_new_ticket_emails_only_active_admin_users(self):
        ticket = self.create()
        self.service.notify_admins_of_new_ticket(ticket)

        recipients, subject, html, text = self.email.sent[0]
        self.assertEqual(recipients, ["admin@example.test"])
        self.assertIn("Chat with Codebase", subject)
        self.assertIn("Chat answers are empty.", html)
        self.assertIn("user@example.test", text)

    def test_status_change_emails_requester(self):
        ticket = self.service.update_status(self.create().id, SupportTicketStatus.COMPLETED, "admin-1")
        self.service.notify_requester_of_status(ticket)

        recipients, subject, html, _ = self.email.sent[0]
        self.assertEqual(recipients, ["user@example.test"])
        self.assertIn("Completed", subject)
        self.assertIn("https://app.example.test/support", html)

    def test_email_failures_are_logged_not_raised(self):
        self.service.email_service = RecordingEmailService(fail=True)
        self.service.notify_admins_of_new_ticket(self.create())

        self.assertEqual(len(self.failures), 1)
        self.assertIn("SMTP unavailable", self.failures[0])

    def test_image_upload_round_trip_and_validation(self):
        url = self.service.store_image("user-1", PNG_BYTES, "http://ignored/")

        self.assertTrue(url.startswith("https://api.example.test/support/uploads/"))
        contents, content_type = self.service.load_image(url.rsplit("/", 1)[1])
        self.assertEqual((contents, content_type), (PNG_BYTES, "image/png"))
        with self.assertRaises(SupportValidationError):
            self.service.store_image("user-1", b"<svg onload=alert(1)>", "http://ignored/")
        with self.assertRaises(SupportValidationError):
            self.service.store_image("user-1", b"", "http://ignored/")


if __name__ == "__main__":
    unittest.main()
