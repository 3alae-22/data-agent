import requests
import pandas as pd

from utils.postgres_util import write_dataframe, read_dataframe
from utils.sandbox_executor import SandboxExecutor


class ETLTools:

    def __init__(self):
        self.sandbox = SandboxExecutor()

    def extract_load(self, url: str, table_name: str, if_exists: str = "replace"):
        """
        Extracts data from an API and loads it into a Postgres table.

        Args:
            url (str): API endpoint.
            table_name (str): target Postgres table.
            if_exists (str): "replace", "append", or "fail".

        Returns:
            str: success or error message.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            return f"Failed to extract data: {e}"
        except ValueError as e:
            return f"Failed to parse API response as JSON: {e}"

        records = data["results"] if isinstance(data, dict) and "results" in data else data

        try:
            df = pd.json_normalize(records)
            return write_dataframe(df, table_name, if_exists=if_exists)
        except Exception as e:
            return f"Failed to transform or load data: {e}"

    def transform_load_context(self, table_name: str):
        """
        Reads an already-loaded Postgres table and returns a preview (3 rows).
        """
        try:
            df = read_dataframe(table_name, limit=3)
            return str(df)
        except Exception as e:
            return f"Failed to read table {table_name}: {e}"

    def execute_code(self, code: str):
        """
        Executes LLM-generated code in an isolated Python container
        (instead of a local exec(); see sandbox_executor.SandboxExecutor).
        """
        return self.sandbox.run(code)


if __name__ == "__main__":
    obj = ETLTools()
    print(obj.extract_load("https://pokeapi.co/api/v2/pokemon/", "pokemon_raw"))
    print(obj.transform_load_context("pokemon_raw"))