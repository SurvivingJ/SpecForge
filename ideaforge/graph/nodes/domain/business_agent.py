import json
import os

from graph.state import ProjectState
from config import get_llm, HAIKU_MODEL, DEPTH_CONFIG

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "prompts", "domain_business.txt")


def business_agent(state: ProjectState) -> dict:
    with open(PROMPT_PATH, "r") as f:
        system_prompt = f.read()

    target_files = ["business.md", "overview.md"]
    wiki_context = ""
    for filename in target_files:
        if filename in state["shadow_wiki"]:
            wiki_context += f"\n--- {filename} ---\n{state['shadow_wiki'][filename]}\n"

    lint_context = ""
    if state.get("lint_warnings"):
        lint_context = "\n## Priority Areas (from Linter)\n" + "\n".join(
            f"- {w}" for w in state["lint_warnings"]
        )

    depth = state["depth"]
    depth_cfg = DEPTH_CONFIG.get(depth, DEPTH_CONFIG["medium"])
    questions_per_agent = depth_cfg["questions_per_agent"]
    quota_instruction = (
        f"Generate exactly {questions_per_agent} questions."
        if questions_per_agent > 0
        else "Generate as many questions as needed to fully specify this domain."
    )

    llm = get_llm(HAIKU_MODEL)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"## Current Shadow Wiki (your target files)\n{wiki_context}\n"
            f"{lint_context}\n"
            f"## Instructions\n"
            f"Depth level: {depth}\n"
            f"Round number: {state['round_number']}\n"
            f"{quota_instruction}"
        )},
    ])

    content = response.content
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        result = json.loads(content)
        questions = result.get("questions", [])
    except (json.JSONDecodeError, KeyError):
        questions = []

    existing = state.get("current_questions", [])
    return {"current_questions": existing + questions}
