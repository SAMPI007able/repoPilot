import base64
import unittest
from unittest.mock import patch

from app.services.repository_services import RepositoryService


class RepositoryServiceAuthTests(unittest.TestCase):
    @patch("git.Repo.clone_from")
    def test_clone_passes_oauth_environment_to_git_process(self, clone_from) -> None:
        service = RepositoryService()

        service.clone_repository(
            "https://user@bitbucket.org/acme/repository.git",
            "/tmp/testforge-auth-test",
            "secret-token",
        )

        clone_url, destination = clone_from.call_args.args
        environment = clone_from.call_args.kwargs["env"]
        self.assertEqual("https://bitbucket.org/acme/repository.git", clone_url)
        self.assertEqual("/tmp/testforge-auth-test", destination)
        self.assertEqual("0", environment["GIT_TERMINAL_PROMPT"])
        self.assertTrue(environment["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic "))

    @patch("git.Repo.clone_from")
    def test_selected_branch_uses_single_branch_clone(self, clone_from) -> None:
        service = RepositoryService()

        service.clone_repository(
            "https://bitbucket.org/acme/repository.git",
            "/tmp/testforge-branch-test",
            authorization="secret-token",
            branch="feature/dashboard",
        )

        self.assertEqual("feature/dashboard", clone_from.call_args.kwargs["branch"])
        self.assertTrue(clone_from.call_args.kwargs["single_branch"])

    @patch("git.Repo.clone_from")
    def test_omitted_branch_preserves_default_clone_behavior(self, clone_from) -> None:
        service = RepositoryService()

        service.clone_repository(
            "https://bitbucket.org/acme/repository.git",
            "/tmp/testforge-default-branch-test",
            authorization="secret-token",
        )

        self.assertNotIn("branch", clone_from.call_args.kwargs)
        self.assertNotIn("single_branch", clone_from.call_args.kwargs)

    def test_bitbucket_oauth_clone_uses_basic_token_auth(self) -> None:
        service = RepositoryService()

        environment = service._git_authorization_environment(
            "https://bitbucket.org/acme/repository.git", "secret-token"
        )

        expected = base64.b64encode(b"x-token-auth:secret-token").decode("ascii")
        self.assertEqual(
            f"Authorization: Basic {expected}", environment["GIT_CONFIG_VALUE_0"]
        )
        self.assertEqual(
            "http.https://bitbucket.org/.extraHeader",
            environment["GIT_CONFIG_KEY_0"],
        )

    def test_provider_username_is_removed_from_clone_url(self) -> None:
        service = RepositoryService()

        clone_url = service._without_url_credentials(
            "https://lahiriarnab4@bitbucket.org/acme/repository.git"
        )

        self.assertEqual(
            "https://bitbucket.org/acme/repository.git",
            clone_url,
        )

    def test_github_and_gitlab_use_provider_specific_basic_usernames(self) -> None:
        service = RepositoryService()

        cases = (
            ("https://github.com/acme/repository.git", "x-access-token"),
            ("https://gitlab.com/acme/repository.git", "oauth2"),
        )
        for url, username in cases:
            with self.subTest(url=url):
                environment = service._git_authorization_environment(url, "token")
                expected = base64.b64encode(f"{username}:token".encode()).decode()
                self.assertEqual(
                    f"Authorization: Basic {expected}",
                    environment["GIT_CONFIG_VALUE_0"],
                )

    @patch("app.services.repository_services.subprocess.run")
    def test_remote_branch_listing_returns_sorted_head_names(self, run) -> None:
        run.return_value.stdout = (
            "abc\trefs/heads/release/v2\n"
            "def\trefs/heads/main\n"
            "ghi\trefs/tags/v1\n"
        )

        branches = RepositoryService().list_remote_branches(
            "https://github.com/acme/repository.git", authorization="token"
        )

        self.assertEqual(branches, ["main", "release/v2"])
        self.assertEqual(
            run.call_args.args[0],
            ["git", "ls-remote", "--heads", "https://github.com/acme/repository.git"],
        )
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")


if __name__ == "__main__":
    unittest.main()
