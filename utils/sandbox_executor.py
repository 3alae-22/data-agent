import os
import tempfile
import uuid

import docker


def _build_database_url() -> str:
    user = os.environ["user"]
    password = os.environ["password"]
    database = os.environ["database"]
    host = os.environ.get("sandbox_host", "postgres")
    return f"postgresql+psycopg2://{user}:{password}@{host}:5432/{database}"


class SandboxExecutor:
    """
    Executes LLM-generated Python code in an isolated and ephemeral Docker
    container.
    """

    def __init__(
        self,
        image: str = "etl-sandbox:latest",
        network: str | None = None,
        timeout: int = 60,
        output_root: str = "../data/outputs",
    ):
        self.client = docker.from_env()
        self.image = image
        self.network = network or os.environ.get("sandbox_network", "data-agent-net")
        self.timeout = timeout
        self.output_root = os.path.abspath(output_root)
        os.makedirs(self.output_root, exist_ok=True)

    def run(self, code: str, input_files: dict[str, str] | None = None) -> str:
        """
        Args:
            code: Python source to execute in the sandbox.
            input_files: optional {filename: content} to mount read-only
                alongside the script (e.g. a raw API JSON payload). The
                generated code can read them via the DATA_PATH env var
                (single file) or INPUT_DIR (multiple files).
        """
        run_id = uuid.uuid4().hex[:8]
        output_dir = os.path.join(self.output_root, run_id)
        os.makedirs(output_dir, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            script_path = os.path.join(tmp, "script.py")
            with open(script_path, "w") as f:
                f.write(code)

            environment = {
                "DATABASE_URL": _build_database_url(),
                "OUTPUT_DIR": "/sandbox_output",
            }

            if input_files:
                for filename, content in input_files.items():
                    with open(os.path.join(tmp, filename), "w") as f:
                        f.write(content)
                if len(input_files) == 1:
                    environment["DATA_PATH"] = f"/sandbox/{next(iter(input_files))}"
                else:
                    environment["INPUT_DIR"] = "/sandbox"

            container = self.client.containers.run(
                self.image,
                command=["python", "/sandbox/script.py"],
                volumes={
                    tmp: {"bind": "/sandbox", "mode": "ro"},
                    output_dir: {"bind": "/sandbox_output", "mode": "rw"},
                },
                network=self.network,
                environment=environment,
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