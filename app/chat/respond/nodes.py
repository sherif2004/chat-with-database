"""Phase 4, respond: turn the query results into the reply."""

from app.chat.common import deps, record_usage
from app.chat.respond.answer import generate_answer
from app.chat.schemas import QueryTable, TableResult
from app.chat.state import GraphState


def generate_answer_node(state: GraphState, config) -> dict:

    timings, debug, _bg = deps(config)
    statements = state["statements"]
    queries = state["queries"]

    answer_inputs = [
        {"sql": stmt, "rows": [dict(zip(query.columns, row)) for row in query.rows]}
        for stmt, query in zip(statements, queries)
    ]

    with timings.step("generate_answer"):
        answer, prompt, usage = generate_answer(state["question"], answer_inputs)
    debug.prompts["generate_answer"] = prompt
    record_usage(debug, "generate_answer", usage)

    result = TableResult(
        queries=[
            QueryTable(sql=stmt, **query.model_dump(exclude={"rows"}), rows=query.rows)
            for stmt, query in zip(statements, queries)
        ],
        answer=answer,
    )

    return {"intent": "data_question", "result": result, "answer": answer}
