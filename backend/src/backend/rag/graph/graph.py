"""LangGraph workflow.

    START → plan ─┬─(legal)──────→ retrieve → select ─┬─→ answer ──→ END
                  │                    ↑               ├─→ broaden ─┘ (once, then retrieve)
                  │                    └── broaden ←───┘
                  │                                    └─→ not_found → END
                  └─(greeting / off_topic)→ chit_chat → END
"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Checkpointer

from backend.rag.graph import nodes
from backend.rag.graph.state import AgentState


def build_graph(checkpointer: Checkpointer = None):
    g = StateGraph(AgentState)
    g.add_node("plan", nodes.plan)
    g.add_node("retrieve", nodes.retrieve)
    g.add_node("select", nodes.select)
    g.add_node("broaden", nodes.broaden)
    g.add_node("answer", nodes.answer)
    g.add_node("chit_chat", nodes.chit_chat)
    g.add_node("not_found", nodes.not_found)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", nodes.route_after_plan, ["retrieve", "chit_chat"])
    g.add_edge("retrieve", "select")
    g.add_conditional_edges("select", nodes.route_after_select,
                            ["answer", "broaden", "not_found"])
    g.add_edge("broaden", "retrieve")
    for terminal in ("answer", "chit_chat", "not_found"):
        g.add_edge(terminal, END)
    return g.compile(checkpointer=checkpointer)
