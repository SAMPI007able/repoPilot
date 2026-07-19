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

    def clone_repository(self, git_url: str, destination_path: str) -> None:
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
        
        try:
            git.Repo.clone_from(git_url, destination_path)
            print(f"Repository cloned from {git_url} to {destination_path}")
        except Exception as e:
            print(f"Failed to clone repository: {e}")
            raise e

    def is_supported_file(self, file_name: str) -> bool:
        return os.path.splitext(file_name)[1].lower() in self.SUPPORTED_EXTENSIONS

    def scan_repository(self, repo_path: str) -> Dict[str, Any]:
        """
        Recursively scan the repository files, filtering by supported extensions.
        Ignored folders: .git, node_modules, dist, coverage, build, .next, .nuxt, vendor, target
        Allowed extensions: .ts, .tsx, .js, .jsx
        """
        files_metadata = []
        total_files = 0
        typescript_count = 0
        javascript_count = 0

        for root, dirs, files in os.walk(repo_path):
            # Prune ignored directories in-place to avoid walking down them
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for file in files:
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
            "stats": {
                "files": total_files,
                "typescript": typescript_count,
                "javascript": javascript_count
            }
        }
