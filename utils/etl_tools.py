import json

import requests

from utils.postgres_util import read_dataframe
from utils.sandbox_executor import SandboxExecutor
from utils.llm_pick import pick_llm
from utils.llm_output import extract_text, clean_python


def _truncate_for_preview(value, max_items: int = 5):
    """Recursively shorten long lists in a JSON-like structure so the LLM
    prompt stays bounded, while preserving the overall shape (dict vs list,
    nesting) so the model can still infer how to reshape the real payload
    (row-oriented list of records vs columnar time series, etc).
    """
    if isinstance(value, dict):
        return {k: _truncate_for_preview(v, max_items) for k, v in value.items()}
    if isinstance(value, list):
        truncated = [_truncate_for_preview(v, max_items) for v in value[:max_items]]
        if len(value) > max_items:
            truncated.append(f"... ({len(value)} items total)")
        return truncated
    return value


class ETLTools:

    def __init__(self):
        self.sandbox = SandboxExecutor()

    def extract_load(self, url: str, table_name: str):
        """
        Extracts data from an API and loads it into a Postgres table.
        The response shape is not assumed in advance: an LLM is shown a
        size-bounded preview of the actual JSON and writes the pandas code
        that reshapes it into a proper table, executed in the sandbox
        against the full (untruncated) payload.

        Args:
            url (str): API endpoint.
            table_name (str): target Postgres table name.

        Returns:
            str: success or error message, including the generated code
                 and its execution result.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            return f"Failed to extract data: {e}"
        except ValueError as e:
            return f"Failed to parse API response as JSON: {e}"

        raw_json = json.dumps(data)
        preview = json.dumps(_truncate_for_preview(data), indent=2, default=str)

        llm = pick_llm("medium")

        prompt = f"""
                You are a Python Data Analyst who uses Pandas and SQLAlchemy.
                The code you write runs in an isolated container that has access
                to the DATABASE_URL environment variable (Postgres connection)
                and to the raw JSON response, saved as a file at the path given
                by the DATA_PATH environment variable.

                Write only Python code, without explanations or comments.

                1. engine = sqlalchemy.create_engine(os.environ["DATABASE_URL"])
                2. Read and parse the full JSON file at os.environ["DATA_PATH"]
                   with the json module (do not rely on the preview below for
                   the actual data, it is truncated).
                3. Inspect its structure and reshape it into a tabular pandas
                   DataFrame with one row per real record. For example: if a
                   key holds several equal-length lists (a columnar/time-series
                   payload), each list should become a column, one row per
                   index; if the payload is a list of objects, each object
                   should become a row.
                4. Save the result to the table "{table_name}" with
                   df.to_sql("{table_name}", engine, if_exists="replace", index=False)

                Here is a truncated preview of the JSON, to show you its shape
                (long lists are cut short; the real file has the full data):
                {preview}
        """

        response_llm = llm.invoke(prompt)
        response_content = extract_text(response_llm.content)
        pandas_code = clean_python(response_content)

        results = self.execute_code(pandas_code, input_files={"data.json": raw_json})

        return f"Data extracted from {url} and loaded into the {table_name} table.\n\nExecuted code:\n{pandas_code}\n\nResult:\n{results}"

    def transform_load_context(self, table_name: str):
        """
        Reads an already-loaded Postgres table and returns a preview (3 rows).
        """
        try:
            df = read_dataframe(table_name, limit=3)
            return str(df)
        except Exception as e:
            return f"Failed to read table {table_name}: {e}"

    def execute_code(self, code: str, input_files: dict | None = None):
        """
        Executes LLM-generated code in an isolated Python container.
        """
        return self.sandbox.run(code, input_files=input_files)


if __name__ == "__main__":
    obj = ETLTools()
    print(obj.extract_load("https://pokeapi.co/api/v2/pokemon/", "pokemon_raw"))
    print(obj.transform_load_context("pokemon_raw"))