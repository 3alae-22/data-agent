from agents.data_agent_decider import supervisor_agent_graph

supervisor = supervisor_agent_graph()
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