import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langchain.tools import tool

from utils.llm_pick import pick_llm
from utils.etl_tools import ETLTools
from models.schema import ETLAgentSchema
from utils.llm_output import clean_python, extract_text


@tool
def extract_load_tool(url: str, table_name: str) -> str:
        """
        Extracts data from an API and loads it into a Postgres table.

        Args:
            url (str): API endpoint.
            table_name (str): target Postgres table name.

        Returns:
            str: success or error message.
        """

        etl_tools = ETLTools()
        return etl_tools.extract_load(url, table_name)

@tool
def transform_load_tool(input_table: str, output_table: str, user_question: str) -> str:
    """
    Transforms data from a Postgres table and saves the result
    to another Postgres table.

    Args:
        input_table (str): source table.
        output_table (str): destination table.
        user_question (str): transformation instructions.

    Returns:
        str: success or error message.
    """
    etl_tools = ETLTools()

    preview = etl_tools.transform_load_context(input_table)

    llm = pick_llm("medium")

    prompt = f"""
                You are a Python Data Analyst who uses Pandas and SQLAlchemy.
                The code you write runs in an isolated container that has access
                to the DATABASE_URL environment variable (Postgres connection).

                Write only Python code, without explanations or comments.

            1. engine = sqlalchemy.create_engine(os.environ["DATABASE_URL"])
                2. Load the source table "{input_table}" with pd.read_sql
                3. Apply the requested transformation
                4. Save the result to the table "{output_table}" with
               df.to_sql("{output_table}", engine, if_exists="replace", index=False)

                User question: {user_question}\n
                Source table preview: {preview}\n

        """

    response = llm.invoke(prompt)
    response_content = extract_text(response.content)

    # Optional cleanup
    pandas_code = clean_python(response_content)

    # Execute the Pandas code
    results = etl_tools.execute_code(pandas_code)

    return f"Data transformed and saved to the {output_table} table. \n\n Executed code: \n {pandas_code} \n\n Result: \n {results}"

# Toolkit
tools = [extract_load_tool, transform_load_tool]

llm = pick_llm("high")
llm_bind = llm.bind_tools(tools)


def llm_node(state: ETLAgentSchema):

    messages = state.messages

    prompt = f"""
            You are a Python Data Analyst who has access to tools that can extract and load, 
            transform and load data. You will be provided with a user's question 
            and you would need to perform the right ETL operations as per the user's question. 
            If the operation is performed then inform the user and end the coversation.
            Here's the chat history: {messages}\n
    """

    final_answer = llm_bind.invoke(prompt)

    return {"messages": [final_answer]}


def tool_node(state: ETLAgentSchema):
    """
    This node is responsible for invoking the appropriate tool based on the user's question and the context provided by the LLM.
    """
    tools_by_name = {tool.name: tool for tool in tools}
    tool_calls = state.messages[-1].tool_calls

    tools_results = []
    for tool_call in tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        tools_results.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))

    return {"messages": tools_results}


# Nodes and edges
etl_analyst_graph = StateGraph(ETLAgentSchema)
etl_analyst_graph.add_node("llm_node", llm_node)
etl_analyst_graph.add_node("tool_node", tool_node)

etl_analyst_graph.add_edge(START, "llm_node")

def is_tool_call(state:ETLAgentSchema):
    tool_calls = state.messages[-1].tool_calls

    if tool_calls:
        return "tool_node"
    else:
        return "end"

etl_analyst_graph.add_conditional_edges(
    "llm_node",is_tool_call,
    {
        "tool_node": "tool_node",
        "end": END
    }
)

etl_analyst_graph.add_edge("tool_node", "llm_node")

etl_analyst = etl_analyst_graph.compile()

if __name__ == "__main__":
    # Compile the graph

    # Graph
    from IPython.display import display, Image
    img = Image(etl_analyst.get_graph().draw_mermaid_png())
    with open("etl_analyst_graph.png", "wb") as f:
        f.write(img.data)

    response = etl_analyst.invoke(
        {"messages":[HumanMessage(content="""I want to extract the data from the API endpoint 'https://archive-api.open-meteo.com/v1/archive?latitude=33.5&longitude=-10.5&daily=wind_speed_10m_max,wind_direction_10m_dominant&start_date=2024-01-01&end_date=2024-01-31&timezone=UTC'
           and save it in the table wind_raw. And also i want to extract the from the API endpoint 'https://marine-api.open-meteo.com/v1/marine?latitude=33.5&longitude=-10.5&daily=wave_height_max,wave_period_max,swell_wave_height_max&start_date=2024-01-01&end_date=2024-01-31&timezone=UTC&cell_selection=sea'
           and save it in another table wave_raw. And then i want to create another table wind_wave_combined that combines the data from both tables and saves it in the new table. The combined table should have the following columns: date, wind_speed_10m_max, wind_direction_10m_dominant, wave_height_max, wave_period_max, swell_wave_height_max.""")]}
    )
 
    print(response)