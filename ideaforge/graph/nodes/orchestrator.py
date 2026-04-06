import json
import os

from langgraph.types import interrupt, Send

from graph.state import ProjectState
from config import get_llm, HAIKU_MODEL

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "orchestrator.txt")

AGENT_NODE_MAP = {
    "compsci": "compsci_agent",
    "design": "design_agent",
    "business": "business_agent",
    "hardware": "hardware_agent",
    "world": "world_agent",
}


def orchestrator_dispatch(state: ProjectState) -> list[Send]:
    """Fan out to active domain agents in parallel via Send API."""
    sends = []
    for agent_name in state["active_agents"]:
        node_name = AGENT_NODE_MAP.get(agent_name)
        if node_name:
            sends.append(Send(node_name, state))
    return sends


def orchestrator_collect(state: ProjectState) -> dict:
    """Collect questions from domain agents, de-duplicate, and interrupt."""
    raw_questions = state.get("current_questions", [])

    if len(raw_questions) > 1:
        # De-duplicate using LLM
        with open(PROMPT_PATH, "r") as f:
            system_prompt = f.read()

        llm = get_llm(HAIKU_MODEL)
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"questions": raw_questions})},
        ])

        content = response.content
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            result = json.loads(content)
            deduped_questions = result["questions"]
        except (json.JSONDecodeError, KeyError):
            deduped_questions = raw_questions
    else:
        deduped_questions = raw_questions

    # Decrement depth quota (skip for abyss mode where quota is -1)
    depth_quota = state["depth_quota_remaining"]
    if depth_quota > 0:
        depth_quota -= 1

    # Interrupt: pause graph and surface questions to user
    user_answers = interrupt({
        "questions": deduped_questions,
        "round": state["round_number"],
        "wiki_status": list(state["active_files"]),
    })

    return {
        "current_questions": deduped_questions,
        "pending_answers": user_answers,
        "depth_quota_remaining": depth_quota,
        "question_history": [{"round": state["round_number"], "questions": deduped_questions}],
    }
