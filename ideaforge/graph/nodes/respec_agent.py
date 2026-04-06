import json
import os

from config import get_llm, SONNET_MODEL

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "respec.txt")


def respec(shadow_wiki: dict[str, str], file: str, selected_text: str, instruction: str) -> str:
    """Standalone respec: rewrites a specific section without re-running the full graph."""
    with open(PROMPT_PATH, "r") as f:
        system_prompt = f.read()

    # Provide the target file content and the full wiki for context
    target_content = shadow_wiki.get(file, "")
    wiki_context = ""
    for fname, content in shadow_wiki.items():
        if fname != file:
            wiki_context += f"\n--- {fname} ---\n{content}\n"

    llm = get_llm(SONNET_MODEL)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"## Target File: {file}\n{target_content}\n\n"
            f"## Selected Text\n{selected_text}\n\n"
            f"## User Instruction\n{instruction}\n\n"
            f"## Other Wiki Files (for context)\n{wiki_context}"
        )},
    ])

    content = response.content
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        if content.startswith("markdown"):
            content = content[8:]
        content = content.strip()

    try:
        result = json.loads(content)
        return result.get("updated_content", target_content)
    except json.JSONDecodeError:
        # If the LLM returned raw markdown instead of JSON, use it directly
        return content
