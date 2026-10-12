import os
import tempfile
import unittest

from app.persistence.database import Database
from app.persistence.feature_flag_persistence_service import (
    FeatureFlagNotFoundError,
    FeatureFlagPersistenceService,
)
from app.persistence.models import UserRow


class FeatureFlagPersistenceTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.database = Database(f"sqlite:///{self.path.replace(os.sep, '/')}")
        self.database.create_schema()
        self.service = FeatureFlagPersistenceService(self.database)
        self.service.ensure_defaults()

    def tearDown(self):
        self.database.close()
        os.unlink(self.path)

    def test_defaults_are_disabled_and_idempotent(self):
        self.service.ensure_defaults()
        self.assertEqual(
            self.service.client_flags(),
            {"ai_generation": True, "code_quality": False, "preview": False, "uploads": True},
        )
        self.assertFalse(self.service.is_enabled("unknown"))

    def test_admin_update_is_persisted(self):
        with self.database.session() as session:
            session.add(UserRow(
                id="admin-user",
                primary_email="admin@example.test",
                status="ACTIVE",
                role="ADMIN",
                email_verified=True,
            ))

        updated = self.service.update("preview", True, "admin-user")

        self.assertTrue(updated.enabled)
        self.assertEqual(updated.updated_by_user_id, "admin-user")
        self.assertTrue(self.service.is_enabled("preview"))

    def test_unknown_flag_cannot_be_updated(self):
        with self.assertRaises(FeatureFlagNotFoundError):
            self.service.update("missing", True, "admin-user")


if __name__ == "__main__":
    unittest.main()
