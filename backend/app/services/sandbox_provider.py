import os
import base64
import shlex
import time
import http.client
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Protocol

from app.models.preview_models import PreviewEnvironment, PreviewStatus


class SandboxExecutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class SandboxResult:
    preview_url: str
    internal_url: str
    provider_state: dict


class SandboxProvider(Protocol):
    def deploy(
        self,
        preview: PreviewEnvironment,
        environment: dict[str, str],
        transition: Callable[[PreviewStatus, str, dict | None], None],
        log: Callable[[str], None],
        repository_authorization: str | None = None,
    ) -> SandboxResult: ...
    def cleanup(self, provider_state: dict, log: Callable[[str], None]) -> None: ...


class LocalDockerSandboxProvider:
    """Trusted-development adapter. It is deliberately not a production isolation boundary."""

    CACHE_ROOT = "/workspace/repo/.testforge-cache"
    PROVIDER_NAME = "local-docker"

    def __init__(self) -> None:
        self.git_image = os.getenv("PREVIEW_GIT_IMAGE", "alpine/git:v2.47.2")
        self.node_image_prefix = os.getenv("PREVIEW_NODE_IMAGE_PREFIX", "node")
        self.public_host = os.getenv("PREVIEW_PUBLIC_HOST", "127.0.0.1")
        self.health_host = os.getenv("PREVIEW_HEALTH_HOST", self.public_host)

    @staticmethod
    def _client():
        try:
            import docker
            return docker.from_env()
        except Exception as exc:
            raise SandboxExecutionError("SANDBOX_UNAVAILABLE", "Docker is unavailable to the preview worker.") from exc

    def deploy(
        self, preview, environment, transition, log,
        repository_authorization: str | None = None,
    ) -> SandboxResult:
        client = self._client()
        suffix = preview.id.replace("-", "")[:16]
        state = {
            "volume": f"tf-preview-{suffix}",
            "buildNetwork": f"tf-preview-build-{suffix}",
            "runtimeNetwork": f"tf-preview-runtime-{suffix}",
            "runtimeContainer": f"tf-preview-app-{suffix}",
        }
        labels = {"testforge.preview_id": preview.id, "testforge.managed": "true"}
        volume = None
        build_network = None
        runtime_network = None
        try:
            volume = client.volumes.create(name=state["volume"], labels=labels)
            build_network = client.networks.create(state["buildNetwork"], driver="bridge", labels=labels)
            runtime_network = client.networks.create(
                state["runtimeNetwork"], driver="bridge", labels=labels
            )
            transition(PreviewStatus.CLONING, "Cloning the immutable repository commit.", state)
            self._run_step(
                client, self.git_image,
                ["clone", "--no-checkout", "--filter=blob:none", preview.repository_url, "/workspace/repo"],
                volume, build_network.name, labels, log, working_dir="/workspace",
                extra_environment=self._git_authorization_environment(
                    preview.repository_url, repository_authorization
                ),
            )
            self._run_step(
                client, self.git_image,
                ["-C", "/workspace/repo", "checkout", "--detach", preview.commit_sha],
                volume, build_network.name, labels, log,
            )

            node_image = f"{self.node_image_prefix}:{preview.manifest.runtime.version}-bookworm-slim"
            self._run_step(
                client, node_image, ["chown", "-R", "node:node", "/workspace/repo"],
                volume, build_network.name, labels, log, user="root", drop_caps=False,
            )
            transition(PreviewStatus.INSTALLING, "Installing locked dependencies in the sandbox.", state)
            self._run_step(
                client, node_image, shlex.split(preview.manifest.install.command),
                volume, build_network.name, labels, log, user="node",
            )
            transition(PreviewStatus.BUILDING, "Building the web application in the sandbox.", state)
            self._run_step(
                client, node_image, shlex.split(preview.manifest.build.command),
                volume, build_network.name, labels, log, user="node",
            )
            self._run_step(
                client, node_image, ["rm", "-rf", "--", self.CACHE_ROOT],
                volume, build_network.name, labels, log, user="node",
            )

            transition(PreviewStatus.STARTING, "Starting the preview service with constrained resources.", state)
            service = next(item for item in preview.manifest.services if item.public)
            runtime_environment = {**environment, "PORT": str(service.port), "HOST": "0.0.0.0", "NODE_ENV": "development"}
            container = client.containers.run(
                node_image,
                shlex.split(service.command),
                name=state["runtimeContainer"],
                detach=True,
                working_dir="/workspace/repo",
                volumes={volume.name: {"bind": "/workspace", "mode": "rw"}},
                network=runtime_network.name,
                ports={f"{service.port}/tcp": ("127.0.0.1", 0)},
                environment=runtime_environment,
                user="node",
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit=self._memory_bytes(preview.manifest.resources.memory_limit),
                nano_cpus=self._nano_cpus(preview.manifest.resources.cpu_limit),
                pids_limit=128,
                labels=labels,
            )
            container.reload()
            binding = container.attrs["NetworkSettings"]["Ports"][f"{service.port}/tcp"][0]
            host_port = int(binding["HostPort"])
            preview_url = f"http://{self.public_host}:{host_port}"
            health_url = f"http://{self.health_host}:{host_port}"
            internal_url = f"http://{container.name}:{service.port}"
            state["hostPort"] = host_port
            transition(PreviewStatus.HEALTH_CHECKING, "Waiting for the preview health check.", state)
            self._wait_for_health(container, health_url + service.healthcheck.path, service.healthcheck.timeout_seconds, log)
            return SandboxResult(preview_url=preview_url, internal_url=internal_url, provider_state=state)
        except SandboxExecutionError:
            try:
                self.cleanup(state, log)
            except SandboxExecutionError:
                pass
            raise
        except Exception as exc:
            try:
                self.cleanup(state, log)
            except SandboxExecutionError:
                pass
            raise SandboxExecutionError(
                "SANDBOX_DEPLOY_FAILED", "Sandbox deployment failed. See preview logs."
            ) from exc

    def cleanup(self, provider_state: dict, log: Callable[[str], None]) -> None:
        client = self._client()
        container_name = provider_state.get("runtimeContainer")
        if container_name:
            try:
                container = client.containers.get(container_name)
                log(self._decode(container.logs(tail=500)))
                container.remove(force=True)
            except Exception:
                pass
        for key in ("runtimeNetwork", "buildNetwork"):
            name = provider_state.get(key)
            if name:
                try:
                    client.networks.get(name).remove()
                except Exception:
                    pass
        volume_name = provider_state.get("volume")
        if volume_name:
            try:
                client.volumes.get(volume_name).remove(force=True)
            except Exception:
                pass

    def _run_step(
        self, client, image, command, volume, network_name, labels, log,
        working_dir="/workspace/repo", user="root", drop_caps=True,
        extra_environment: dict[str, str] | None = None,
    ) -> None:
        security = {
            "cap_drop": ["ALL"] if drop_caps else [],
            "security_opt": ["no-new-privileges:true"],
        }
        cache_environment = {
            "HOME": f"{self.CACHE_ROOT}/home",
            "npm_config_cache": f"{self.CACHE_ROOT}/npm",
            "YARN_CACHE_FOLDER": f"{self.CACHE_ROOT}/yarn",
            "YARN_GLOBAL_FOLDER": f"{self.CACHE_ROOT}/yarn-global",
            "XDG_CACHE_HOME": f"{self.CACHE_ROOT}/xdg",
            "COREPACK_HOME": f"{self.CACHE_ROOT}/corepack",
        }
        cache_environment.update(extra_environment or {})
        container = client.containers.run(
            image, command, detach=True, working_dir=working_dir,
            volumes={volume.name: {"bind": "/workspace", "mode": "rw"}},
            network=network_name, read_only=True,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=128m"},
            environment=cache_environment, user=user,
            mem_limit="2g", nano_cpus=2_000_000_000, pids_limit=256, labels=labels,
            **security,
        )
        try:
            result = container.wait(timeout=900)
            output = self._decode(container.logs(stdout=True, stderr=True))
            log(output)
        finally:
            try:
                container.remove(force=True)
            except Exception:
                pass
        if result.get("StatusCode") != 0:
            if "ENOSPC" in output or "no space left on device" in output.lower():
                raise SandboxExecutionError(
                    "SANDBOX_STORAGE_EXHAUSTED",
                    "The sandbox ran out of storage while installing or building dependencies.",
                )
            raise SandboxExecutionError("SANDBOX_COMMAND_FAILED", "A sandbox build command failed. See preview logs.")

    @staticmethod
    def _wait_for_health(container, url: str, timeout_seconds: int, log) -> None:
        deadline = time.monotonic() + timeout_seconds
        last_error = "not ready"
        while time.monotonic() < deadline:
            container.reload()
            if container.status not in {"created", "running"}:
                log(LocalDockerSandboxProvider._decode(container.logs(tail=500)))
                raise SandboxExecutionError("PREVIEW_STARTUP_FAILED", f"Preview exited with status {container.status}.")
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 500:
                        return
            except urllib.error.HTTPError as exc:
                if exc.code < 500:
                    return
                last_error = str(exc)
            except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
                last_error = str(exc)
            time.sleep(1)
        log(LocalDockerSandboxProvider._decode(container.logs(tail=500)))
        raise SandboxExecutionError("PREVIEW_HEALTH_TIMEOUT", f"Preview health check timed out: {last_error}")

    @staticmethod
    def _decode(value) -> str:
        return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)

    @staticmethod
    def _memory_bytes(value: str) -> int:
        units = {"Mi": 1024**2, "Gi": 1024**3}
        for suffix, multiplier in units.items():
            if value.endswith(suffix):
                return int(value[:-2]) * multiplier
        raise SandboxExecutionError("RESOURCE_LIMIT_INVALID", "Unsupported memory limit.")

    @staticmethod
    def _nano_cpus(value: str) -> int:
        return int(value[:-1]) * 1_000_000 if value.endswith("m") else int(value) * 1_000_000_000

    @staticmethod
    def _git_authorization_environment(git_url: str, token: str | None) -> dict[str, str]:
        if not token:
            return {"GIT_TERMINAL_PROMPT": "0"}
        parsed = urllib.parse.urlsplit(git_url)
        username = {
            "github.com": "x-access-token",
            "www.github.com": "x-access-token",
            "gitlab.com": "oauth2",
            "bitbucket.org": "x-token-auth",
        }.get((parsed.hostname or "").lower())
        if not username:
            raise SandboxExecutionError(
                "REPOSITORY_AUTH_UNSUPPORTED",
                "Authenticated preview cloning is not supported for this Git host.",
            )
        credentials = base64.b64encode(f"{username}:{token}".encode()).decode("ascii")
        origin = f"{parsed.scheme}://{parsed.netloc}/"
        return {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"http.{origin}.extraHeader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credentials}",
        }
