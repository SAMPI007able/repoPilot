import os
import tempfile
import unittest

from app.persistence.database import Database
from app.persistence.models import UserRow, WorkspaceRow
from app.persistence.test_generation_persistence_service import TestGenerationPersistenceService


class TestGenerationPersistenceTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.database = Database(f"sqlite:///{self.path.replace(os.sep, '/')}")
        self.database.create_schema()
        with self.database.session() as session:
            session.add(UserRow(
                id="user", primary_email="user@example.test", status="ACTIVE",
                role="USER", email_verified=True,
            ))
            session.add(WorkspaceRow(
                id="workspace", owner_user_id="user", repo_url="https://example.test/repo",
                repo_name="repo", status="ready", stats={},
            ))
        self.service = TestGenerationPersistenceService(self.database)

    def tearDown(self):
        self.database.close()
        os.unlink(self.path)

    def test_generation_is_scoped_listed_and_reusable_by_hash(self):
        created = self.service.create(
            user_id="user", workspace_id="workspace", mode="scenario",
            test_type="integration", target=None, scenario="retry payment",
            prompt="prompt", markdown="# tests", request_hash="same-request",
        )

        listed = self.service.list_generations("user", "workspace")
        cached = self.service.find_cached("user", "workspace", "same-request")
        restored = self.service.get_generation(created.id, "user", "workspace")

        self.assertEqual([item.id for item in listed], [created.id])
        self.assertEqual(listed[0].scenario, "retry payment")
        self.assertEqual(cached.markdown, "# tests")
        self.assertEqual(restored.markdown, "# tests")
        self.assertIsNone(self.service.get_generation(created.id, "other-user", "workspace"))
        self.assertIsNone(self.service.find_cached("other-user", "workspace", "same-request"))


if __name__ == "__main__":
    unittest.main()
