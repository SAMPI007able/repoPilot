import base64
import os
import shutil
import stat
import urllib.parse
from typing import Dict, Any


class RepositoryService:
    IGNORE_DIRS = {
        '.git', 'node_modules', 'dist', 'coverage',
        'build', '.next', '.nuxt', 'vendor', 'target'
    }
    SUPPORTED_EXTENSIONS = {'.ts', '.tsx', '.js', '.jsx'}
    RUNTIME_SIGNAL_FILES = {
        "package.json", "package-lock.json", "npm-shrinkwrap.json",
        "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
        "dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "compose.yml", "compose.yaml", "procfile", ".nvmrc",
        ".node-version", ".env.example", ".env.sample",
    }

    def _handle_remove_readonly(self, func, path, exc_info):
        """Error handler for shutil.rmtree to change read-only file permissions and retry."""
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception as e:
            print(f"Failed to remove read-only file/folder {path}: {e}")

    def extract_repo_name(self, git_url: str) -> str:
        """
        Extract repository name from a Git URL.
        """
        parsed = urllib.parse.urlparse(git_url)
        path = parsed.path.rstrip('/')
        repo_name = path.split('/')[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        return repo_name

    def validate_public_repository_url(self, git_url: str) -> str:
        parsed = urllib.parse.urlparse(git_url.strip())
        if parsed.scheme != "https":
            raise ValueError("Repository URL must use HTTPS.")
        if parsed.username or parsed.password:
            raise ValueError("Repository URL must not contain credentials.")
        if (parsed.hostname or "").lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Only public GitHub repository URLs are supported.")
        if parsed.port not in {None, 443}:
            raise ValueError("Repository URL must use the standard HTTPS port.")
        path_segments = [segment for segment in parsed.path.split("/") if segment]
        if len(path_segments) != 2:
            raise ValueError("Repository URL must identify a GitHub owner and repository.")
        if parsed.query or parsed.fragment:
            raise ValueError("Repository URL must not include query parameters or fragments.")
        return git_url.strip()

    def clone_repository(
        self,
        git_url: str,
        destination_path: str,
        authorization: str | None = None,
        branch: str | None = None,
    ) -> None:
        """
        Clone a Git repository from the given URL to the specified destination path.
        If the directory already exists, clear it first.

        :param git_url: The URL of the Git repository to clone.
        :param destination_path: The local path where the repository should be cloned.
        """
        import git  # Importing here to avoid unnecessary dependency if not used

        if os.path.exists(destination_path):
            print(f"Directory {destination_path} already exists. Cleaning it...")
            try:
                shutil.rmtree(destination_path, onerror=self._handle_remove_readonly)
            except Exception as e:
                print(f"Failed to clear directory {destination_path}: {e}")
                # We can try to proceed anyway or raise
        
        clone_url = self._without_url_credentials(git_url)

        try:
            environment = {"GIT_TERMINAL_PROMPT": "0"}
            if authorization:
                environment.update(self._git_authorization_environment(clone_url, authorization))
            clone_options = {"branch": branch, "single_branch": True} if branch else {}
            git.Repo.clone_from(
                clone_url,
                destination_path,
                env=environment,
                **clone_options,
            )
            print(f"Repository cloned from {clone_url} to {destination_path}")
        except Exception as e:
            print(f"Failed to clone repository: {e}")
            raise e

    @staticmethod
    def _without_url_credentials(git_url: str) -> str:
        """Remove provider-supplied user info so Git never prompts for a missing password."""
        parsed = urllib.parse.urlsplit(git_url.strip())
        if not parsed.hostname:
            return git_url.strip()
        hostname = parsed.hostname
        if ":" in hostname:
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc += f":{parsed.port}"
        return urllib.parse.urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )

    @staticmethod
    def _git_authorization_environment(git_url: str, token: str) -> dict[str, str]:
        """Build a host-scoped Git auth header for supported OAuth providers."""
        parsed = urllib.parse.urlsplit(git_url)
        hostname = (parsed.hostname or "").lower()
        basic_usernames = {
            "bitbucket.org": "x-token-auth",
            "github.com": "x-access-token",
            "www.github.com": "x-access-token",
            "gitlab.com": "oauth2",
        }
        username = basic_usernames.get(hostname)
        if username:
            credentials = base64.b64encode(
                f"{username}:{token}".encode("utf-8")
            ).decode("ascii")
            header = f"Authorization: Basic {credentials}"
        else:
            header = f"Authorization: Bearer {token}"

        origin = f"{parsed.scheme}://{parsed.netloc}/"
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"http.{origin}.extraHeader",
            "GIT_CONFIG_VALUE_0": header,
        }

    def get_commit_sha(self, repository_path: str) -> str | None:
        try:
            import git

            return git.Repo(repository_path).head.commit.hexsha
        except Exception:
            return None

    def delete_repository(self, repository_path: str) -> None:
        if not os.path.exists(repository_path):
            return
        shutil.rmtree(repository_path, onerror=self._handle_remove_readonly)
        if os.path.exists(repository_path):
            raise RuntimeError(f"Failed to remove temporary repository: {repository_path}")

    def is_supported_file(self, file_name: str) -> bool:
        return os.path.splitext(file_name)[1].lower() in self.SUPPORTED_EXTENSIONS

    def scan_repository(self, repo_path: str) -> Dict[str, Any]:
        """
        Recursively scan the repository files, filtering by supported extensions.
        Ignored folders: .git, node_modules, dist, coverage, build, .next, .nuxt, vendor, target
        Allowed extensions: .ts, .tsx, .js, .jsx
        """
        files_metadata = []
        runtime_files = []
        total_files = 0
        typescript_count = 0
        javascript_count = 0

        for root, dirs, files in os.walk(repo_path):
            # Prune ignored directories in-place to avoid walking down them
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for file in files:
                relative_candidate = os.path.relpath(
                    os.path.join(root, file), repo_path
                ).replace('\\', '/')
                if self._is_runtime_signal_file(relative_candidate):
                    runtime_files.append(relative_candidate)
                if not self.is_supported_file(file):
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_path).replace('\\', '/')
                ext = os.path.splitext(file)[1].lower()

                try:
                    size = os.path.getsize(full_path)
                except OSError:
                    size = 0

                files_metadata.append({
                    "name": file,
                    "path": rel_path,
                    "absolute_path": full_path,
                    "extension": ext,
                    "size": size
                })

                total_files += 1
                if ext in {'.ts', '.tsx'}:
                    typescript_count += 1
                elif ext in {'.js', '.jsx'}:
                    javascript_count += 1

        return {
            "files": files_metadata,
            "runtime_files": sorted(runtime_files)[:500],
            "stats": {
                "files": total_files,
                "typescript": typescript_count,
                "javascript": javascript_count
            }
        }

    def _is_runtime_signal_file(self, relative_path: str) -> bool:
        file_name = os.path.basename(relative_path).lower()
        if file_name in self.RUNTIME_SIGNAL_FILES:
            return True
        return file_name.startswith(
            ("vite.config.", "next.config.", "nuxt.config.", "vue.config.")
        )
