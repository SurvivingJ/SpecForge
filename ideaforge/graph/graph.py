from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from graph.state import ProjectState
from graph.nodes.structure_agent import structure_agent
from graph.nodes.orchestrator import orchestrator_dispatch, orchestrator_collect
from graph.nodes.synthesizer import synthesizer_agent
from graph.nodes.linter import structure_linter_agent
from graph.nodes.finaliser import finaliser_node
from graph.nodes.domain.compsci_agent import compsci_agent


from graph.nodes.domain.design_agent import design_agent
from graph.nodes.domain.business_agent import business_agent
from graph.nodes.domain.hardware_agent import hardware_agent
from graph.nodes.domain.world_agent import world_agent


def route_after_synthesis(state: ProjectState) -> str:
    if state.get("is_complete") or state.get("depth_quota_remaining", 0) == 0:
        return "finaliser"
    return "linter"


def route_after_linter(state: ProjectState) -> str:
    return "orchestrator_dispatch"


def build_graph() -> StateGraph:
    graph = StateGraph(ProjectState)

    # Add nodes
    graph.add_node("structure_agent", structure_agent)
    graph.add_node("orchestrator_dispatch", orchestrator_dispatch)
    graph.add_node("orchestrator_collect", orchestrator_collect)
    graph.add_node("synthesizer", synthesizer_agent)
    graph.add_node("linter", structure_linter_agent)
    graph.add_node("finaliser", finaliser_node)

    # Domain agent nodes
    graph.add_node("compsci_agent", compsci_agent)
    graph.add_node("design_agent", design_agent)
    graph.add_node("business_agent", business_agent)
    graph.add_node("hardware_agent", hardware_agent)
    graph.add_node("world_agent", world_agent)

    # Edges
    graph.add_edge(START, "structure_agent")
    graph.add_edge("structure_agent", "orchestrator_dispatch")

    # orchestrator_dispatch returns Send() objects to fan out to domain agents
    # Domain agents all flow back to orchestrator_collect
    graph.add_edge("compsci_agent", "orchestrator_collect")
    graph.add_edge("design_agent", "orchestrator_collect")
    graph.add_edge("business_agent", "orchestrator_collect")
    graph.add_edge("hardware_agent", "orchestrator_collect")
    graph.add_edge("world_agent", "orchestrator_collect")

    # After interrupt/resume, orchestrator_collect -> synthesizer
    graph.add_edge("orchestrator_collect", "synthesizer")

    # Conditional: after synthesis, either loop back or finalise
    graph.add_conditional_edges("synthesizer", route_after_synthesis, {
        "finaliser": "finaliser",
        "linter": "linter",
    })

    graph.add_conditional_edges("linter", route_after_linter, {
        "orchestrator_dispatch": "orchestrator_dispatch",
    })

    graph.add_edge("finaliser", END)

    return graph


def create_compiled_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = MemorySaver()
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer), checkpointer
