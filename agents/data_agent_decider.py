import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

from etl_agent import etl_analyst_graph
from sql_analyst import sql_agent_graph
from plot_agent import plot_agent_graph
from models.schema import SupervisorSchema, RouteSchema
from utils.llm_pick import pick_llm
from utils.llm_output import extract_text

from langgraph.types import RetryPolicy
from langchain_google_genai.chat_models import GoogleAPIError


def router_node(state: SupervisorSchema):
    llm = pick_llm("high")
    llm_router = llm.with_structured_output(RouteSchema)

    prompt = f"""
    You are a routing agent that decides which workflow to run NEXT, given the conversation and workflow history so far.
    The possible workflows are:
    1. ETL: Extracts/transforms data into Postgres tables.
    2. SQL: Answers questions by querying data already in Postgres.
    3. PLOT: Visualizes data already in Postgres and saves an image file.
    Return 'DONE' once enough data or information already exists to fully answer the user's original question and no further workflow is needed.
    The user's original question is: {state.user_question}\n
    The context of the conversation and workflow history so far is: {state.messages}\n

    Progress so far (empty means that workflow has not run yet — do not re-run a
    workflow that already has a result below unless it clearly failed or the result
    is incomplete/irrelevant to the original question):
    - ETL result: {state.etl_response or "(not run)"}
    - SQL result: {state.sql_response or "(not run)"}
    - PLOT result: {state.plot_response or "(not run)"}

    Important: ETL and SQL cannot create image files or plots — only the PLOT workflow
    can. If the user's original question asks for a plot, chart, graph, or saved image
    file, and "PLOT result" above is "(not run)", you MUST route to PLOT next. This
    applies even if the ETL or SQL result above says visualization/plotting is outside
    its own capabilities — that limitation is specific to that workflow's tools, not to
    the PLOT workflow. Only return 'DONE' once every distinct deliverable the user asked
    for (e.g. data loaded, question answered, AND plot saved, whichever apply) has a
    non-empty, successful result above.

    You can use all the information available to you to make the best decision on which workflow to run NEXT. Please provide a short rationale for your routing decision.
    """

    user_question = state.user_question
    route_response_dict = llm_router.invoke(prompt).model_dump()
    route_response = route_response_dict['answer']

    messages_update = [] if state.messages else [HumanMessage(content=user_question)]

    return {"route_response": route_response, "messages": messages_update}


def sql_node(state: SupervisorSchema):
    user_question = state.user_question

    sql_analyst = sql_agent_graph()

    input_schema = {
        "messages": [],
        "user_question": f"{user_question}",
        "curated_ques": "",
        "prompt_query_context": "",
        "generated_sql_query": "",
        "is_safe": "No",
        "comments": "",
        "sql_query_execution_result": "",
        "final_answer": ""
    }

    response = sql_analyst.invoke(input_schema)
    sql_response = response["final_answer"]

    # Forward everything the SQL sub-graph accumulated in `messages` (started
    # empty here, so nothing to strip) instead of only a synthetic summary —
    # same reasoning as etl_node/plot_node below.
    new_messages = response["messages"]

    return {"messages": new_messages, "sql_response": sql_response}


def etl_node(state: SupervisorSchema):
    user_question = state.user_question

    etl_agent = etl_analyst_graph()

    seed_messages = [HumanMessage(content=user_question)]
    response = etl_agent.invoke({"messages": seed_messages})

    # Forward the full trace (tool calls + real tool results), not just the
    # sub-agent's final summary: this is what lets the router (or a human
    # reading the log) catch a sub-agent claiming success on something no
    # tool call actually confirmed. Only the seed HumanMessage we just fed
    # in gets stripped, since the supervisor's own `messages` already carries
    # an equivalent one from router_node's first turn.
    new_messages = response["messages"][len(seed_messages):]
    etl_response = extract_text(new_messages[-1].content) if new_messages else ""

    return {"messages": new_messages, "etl_response": etl_response}


def plot_node(state: SupervisorSchema):
    user_question = state.user_question

    plot_agent = plot_agent_graph()

    seed_messages = [HumanMessage(content=user_question)]
    response = plot_agent.invoke({"messages": seed_messages})

    new_messages = response["messages"][len(seed_messages):]
    plot_response = extract_text(new_messages[-1].content) if new_messages else ""

    return {"messages": new_messages, "plot_response": plot_response}


def supervisor_agent_graph():
    supervisor_analyst_graph = StateGraph(SupervisorSchema)

    supervisor_analyst_graph.add_node(
        "router_node",
        router_node,
        retry_policy = RetryPolicy(
            max_attempts=5,
            initial_interval=2.0,
            backoff_factor=2.0,
            max_interval=60.0,
            jitter=True,
            retry_on=(GoogleAPIError,),
        ),
    )
    supervisor_analyst_graph.add_node("sql_node", sql_node)
    supervisor_analyst_graph.add_node("etl_node", etl_node)
    supervisor_analyst_graph.add_node("plot_node", plot_node)

    supervisor_analyst_graph.add_edge(START, "router_node")

    def route_from_router(state: SupervisorSchema) -> str:
        return state.route_response

    supervisor_analyst_graph.add_conditional_edges(
        "router_node",
        route_from_router,
        {
            "ETL": "etl_node",
            "SQL": "sql_node",
            "PLOT": "plot_node",
            "DONE": END,
        },
    )

    supervisor_analyst_graph.add_edge("etl_node", "router_node")
    supervisor_analyst_graph.add_edge("sql_node", "router_node")
    supervisor_analyst_graph.add_edge("plot_node", "router_node")

    return supervisor_analyst_graph.compile()

if __name__ == "__main__":
    supervisor = supervisor_agent_graph()
    # from IPython.display import display, Image
    # img = Image(supervisor.get_graph().draw_mermaid_png())
    # with open("supervisor.png", "wb") as f:
    #     f.write(img.data)
    response = supervisor.invoke(
        {
            "messages": [],
            "user_question": """Extract wind data (wind_speed_10m_max, wind_direction_10m_dominant) for
        Marrakech (latitude 31.6, longitude -8.0) from 2024-02-01 to 2024-02-10 from
        'https://archive-api.open-meteo.com/v1/archive?latitude=31.6&longitude=-8.0&daily=wind_speed_10m_max,wind_direction_10m_dominant&start_date=2024-02-01&end_date=2024-02-10&timezone=UTC'
        and save it in a table called wind_test.
        Then tell me which day had the strongest wind.
        Finally, plot wind_speed_10m_max over time and save it as wind_test_plot.png.""",
            "route_response": "",
            "sql_response": "",
            "etl_response": "",
            "plot_response": "",
        },
        config={"recursion_limit": 10},
    )
    print(response)