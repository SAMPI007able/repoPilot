import unittest

from app.services.sandbox_provider import LocalDockerSandboxProvider, SandboxExecutionError


class _Container:
    def __init__(self, status_code=0, output=b"") -> None:
        self.status_code = status_code
        self.output = output
        self.removed = False

    def wait(self, timeout):
        return {"StatusCode": self.status_code}

    def logs(self, **kwargs):
        return self.output

    def remove(self, force=False):
        self.removed = force


class _Containers:
    def __init__(self, container) -> None:
        self.container = container
        self.run_kwargs = None

    def run(self, image, command, **kwargs):
        self.run_kwargs = kwargs
        return self.container


class _Client:
    def __init__(self, container) -> None:
        self.containers = _Containers(container)


class _Volume:
    name = "preview-volume"


class SandboxProviderTests(unittest.TestCase):
    def test_package_manager_caches_use_preview_volume(self) -> None:
        container = _Container()
        client = _Client(container)

        LocalDockerSandboxProvider()._run_step(
            client, "node:22", ["yarn", "install"], _Volume(), "build-network", {}, lambda _: None,
            user="node",
        )

        environment = client.containers.run_kwargs["environment"]
        self.assertEqual("/workspace/repo/.testforge-cache/home", environment["HOME"])
        self.assertEqual("/workspace/repo/.testforge-cache/yarn", environment["YARN_CACHE_FOLDER"])
        self.assertEqual("/workspace/repo/.testforge-cache/npm", environment["npm_config_cache"])
        self.assertNotIn("/tmp", " ".join(environment.values()))
        self.assertTrue(container.removed)

    def test_enospc_has_specific_error_and_removes_container(self) -> None:
        container = _Container(1, b"ENOSPC: no space left on device")
        client = _Client(container)

        with self.assertRaises(SandboxExecutionError) as raised:
            LocalDockerSandboxProvider()._run_step(
                client, "node:22", ["yarn", "install"], _Volume(), "build-network", {}, lambda _: None,
            )

        self.assertEqual("SANDBOX_STORAGE_EXHAUSTED", raised.exception.code)
        self.assertTrue(container.removed)


if __name__ == "__main__":
    unittest.main()
