import os
import tempfile
import uuid

import docker

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _build_database_url() -> str:
    user = os.environ["user"]
    password = os.environ["password"]
    database = os.environ["database"]
    host = os.environ.get("sandbox_host", "postgres")
    return f"postgresql+psycopg2://{user}:{password}@{host}:5432/{database}"


class SandboxExecutor:
    """
    Executes LLM-generated Python code in an isolated and ephemeral Docker
    container instead of a local exec() (see the security note in
    execute_code).
    """

    def __init__(
        self,
        image: str = "etl-sandbox:latest",
        network: str | None = None,
        timeout: int = 60,
        output_root: str = os.path.join(_PROJECT_ROOT, "data", "outputs"),
    ):
        self.client = docker.from_env()
        self.image = image
        self.network = network or os.environ.get("sandbox_network", "data-agent-net")
        self.timeout = timeout
        self.output_root = os.path.abspath(output_root)
        os.makedirs(self.output_root, exist_ok=True)

    def run(self, code: str, output_subdir: str | None = None) -> str:
        output_dir = (
            os.path.join(self.output_root, output_subdir)
            if output_subdir
            else os.path.join(self.output_root, uuid.uuid4().hex[:8])
        )
        os.makedirs(output_dir, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            script_path = os.path.join(tmp, "script.py")
            with open(script_path, "w") as f:
                f.write(code)

            container = self.client.containers.run(
                self.image,
                command=["python", "/sandbox/script.py"],
                volumes={
                    tmp: {"bind": "/sandbox", "mode": "ro"},
                    output_dir: {"bind": "/sandbox_output", "mode": "rw"},
                },
                network=self.network,
                environment={
                    "DATABASE_URL": _build_database_url(),
                    "OUTPUT_DIR": "/sandbox_output",
                },
                mem_limit="512m",
                nano_cpus=int(0.5 * 1_000_000_000),
                detach=True,
            )

            try:
                exit_status = container.wait(timeout=self.timeout)
                logs = container.logs().decode("utf-8", errors="replace")
            except Exception:
                container.kill()
                logs = container.logs().decode("utf-8", errors="replace")
                container.remove(force=True)
                return f"Execution timed out after {self.timeout}s.\n{logs}"

            container.remove(force=True)

        generated = sorted(os.listdir(output_dir)) if os.path.isdir(output_dir) else []
        files_section = (
            "\nGenerated files:\n" + "\n".join(f"- {os.path.join(output_dir, f)}" for f in generated)
            if generated else ""
        )

        if exit_status.get("StatusCode", 1) != 0:
            return f"Execution failed:\n{logs}{files_section}"
        return f"Code executed successfully.\n{logs}{files_section}"