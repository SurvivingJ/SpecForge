import json
import os

from graph.state import ProjectState
from config import get_llm, SONNET_MODEL

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "synthesizer.txt")


def synthesizer_agent(state: ProjectState) -> dict:
    with open(PROMPT_PATH, "r") as f:
        system_prompt = f.read()

    # Build context: current wiki state + pending answers
    wiki_context = ""
    for filename, content in state["shadow_wiki"].items():
        wiki_context += f"\n--- {filename} ---\n{content}\n"

    answers_context = json.dumps(state["pending_answers"], indent=2)

    llm = get_llm(SONNET_MODEL)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"## Current Shadow Wiki\n{wiki_context}\n\n"
            f"## User Answers (this round)\n{answers_context}"
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
        updated_files = result.get("updated_files", {})
    except (json.JSONDecodeError, KeyError):
        updated_files = {}

    # Merge updates into existing wiki
    new_wiki = dict(state["shadow_wiki"])
    for filename, new_content in updated_files.items():
        if filename in new_wiki:
            new_wiki[filename] = new_content

    return {
        "shadow_wiki": new_wiki,
        "round_number": state["round_number"] + 1,
        "pending_answers": [],
    }
