import os
import tempfile
import unittest

from app.persistence.chat_persistence_service import ChatPersistenceService, ChatSessionNotFoundError
from app.persistence.database import Database
from app.persistence.models import UserRow, WorkspaceRow


class ChatPersistenceTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.database = Database(f"sqlite:///{self.path.replace(os.sep, '/')}")
        self.database.create_schema()
        with self.database.session() as session:
            session.add(UserRow(id="user", primary_email="user@example.test", status="ACTIVE", role="USER", email_verified=True))
            session.add(WorkspaceRow(id="workspace", owner_user_id="user", repo_url="https://example.test/repo", repo_name="repo", status="ready", stats={}))
        self.service = ChatPersistenceService(self.database)

    def tearDown(self):
        self.database.close()
        os.unlink(self.path)

    def test_exchange_is_restored_as_latest_workspace_session(self):
        chat = self.service.create("user", "workspace")
        self.service.append_exchange(chat.id, "user", "workspace", "Where is auth?", "In auth.py")

        restored = self.service.latest("user", "workspace")

        self.assertEqual(restored.id, chat.id)
        self.assertEqual([(message.role, message.content) for message in restored.messages], [
            ("user", "Where is auth?"), ("assistant", "In auth.py"),
        ])
        self.assertEqual(self.service.context(chat.id, "user", "workspace"), [
            ("user", "Where is auth?"), ("assistant", "In auth.py"),
        ])

    def test_session_cannot_cross_user_boundary(self):
        chat = self.service.create("user", "workspace")
        with self.assertRaises(ChatSessionNotFoundError):
            self.service.get(chat.id, "other-user", "workspace")


if __name__ == "__main__":
    unittest.main()
