import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langchain.tools import tool

from utils.llm_pick import pick_llm
from utils.etl_tools import ETLTools
from models.schema import ETLAgentSchema, VisualizerSchema
from utils.llm_output import clean_python


@tool
def visualizer_tool(table_name: str, user_question: str, output_path: str) -> str:
    """
    Visualizes data from a Postgres table using Matplotlib and saves the
    resulting image file.

    Args:
        table_name (str): source Postgres table to visualize.
        user_question (str): what to plot / visualization instructions.
        output_path (str): filename for the saved image, e.g. "plot.png".

    Returns:
        str: success or error message.
    """
    etl_tools = ETLTools()

    preview = etl_tools.transform_load_context(table_name)

    llm = pick_llm("medium")
    llm_visualizer = llm.with_structured_output(VisualizerSchema)

    prompt = f"""
                You are a Python Data Analyst who uses Pandas and Matplotlib
                to visualize data. The code you write runs in an isolated
                container that has access to the DATABASE_URL environment
                variable (Postgres connection) and to the OUTPUT_DIR
                environment variable, a writable folder for saved files.

                Write only Python code, without explanations or comments,
                for each field.

                pandas_code:
                1. engine = sqlalchemy.create_engine(os.environ["DATABASE_URL"])
                2. Load the table "{table_name}" with pd.read_sql into a
                   DataFrame named df

                matplotlib_code:
                3. Using the DataFrame df already created by pandas_code,
                   build the visualization requested below with matplotlib
                4. Save the figure with
                   plt.savefig(os.path.join(os.environ["OUTPUT_DIR"], "{output_path}"))

                User's visualization request: {user_question}
                Source table preview: {preview}
    """

    response = llm_visualizer.invoke(prompt)
    pandas_code = clean_python(response.pandas_code)
    matplotlib_code = clean_python(response.matplotlib_code)

    # Both parts must run in the SAME sandbox execution: execute_code spins
    # up a fresh, isolated container per call, so a second separate call
    # would not see the `df` created by pandas_code.
    results = etl_tools.execute_code(f"{pandas_code}\n{matplotlib_code}", output_subdir="plots")

    return f"Visualization saved as {output_path}.\n\nExecuted code:\n{pandas_code}\n{matplotlib_code}\n\nResult:\n{results}"


# Toolkit
tools = [visualizer_tool]

llm = pick_llm("high")
llm_bind = llm.bind_tools(tools)


def llm_node(state: ETLAgentSchema):

    messages = state.messages

    prompt = f"""
            You are a Python Data Analyst who has access to a tool that visualizes
            data already stored in Postgres. This is the ONLY thing you are able to
            do — you have no tool to extract/load data, and no tool to query/analyze
            data for an answer.

            Use your tool to perform exactly the visualization the user's question
            asks for. Once done, summarize ONLY what your tool call actually
            confirmed, based on its real result — never invent numbers, dates,
            statistics, or table names that no tool call produced. If part of the
            user's question requires extraction or analysis, say plainly that this
            part is outside what you can do and leave it unaddressed — do not claim
            it was done.

            Here's the chat history: {messages}\n
    """

    final_answer = llm_bind.invoke(prompt)

    return {"messages": [final_answer]}


def tool_node(state: ETLAgentSchema):
    """
    This node is responsible for invoking the appropriate tool based on the
    user's question and the context provided by the LLM.
    """
    tools_by_name = {tool.name: tool for tool in tools}
    tool_calls = state.messages[-1].tool_calls

    tools_results = []
    for tool_call in tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        tools_results.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))

    return {"messages": tools_results}


def plot_agent_graph():
    # Nodes and edges
    plot_analyst_graph = StateGraph(ETLAgentSchema)
    plot_analyst_graph.add_node("llm_node", llm_node)
    plot_analyst_graph.add_node("tool_node", tool_node)

    plot_analyst_graph.add_edge(START, "llm_node")

    def is_tool_call(state: ETLAgentSchema):
        tool_calls = state.messages[-1].tool_calls

        if tool_calls:
            return "tool_node"
        else:
            return "end"

    plot_analyst_graph.add_conditional_edges(
        "llm_node", is_tool_call,
        {
            "tool_node": "tool_node",
            "end": END
        }
    )

    plot_analyst_graph.add_edge("tool_node", "llm_node")

    plot_analyst = plot_analyst_graph.compile()

    return plot_analyst