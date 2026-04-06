import json
import re

from graph.state import ProjectState
from config import get_llm, HAIKU_MODEL


def structure_linter_agent(state: ProjectState) -> dict:
    """Periodic health-check: scans Shadow Wiki for inconsistencies."""
    # Only run every 2 rounds
    if state["round_number"] < 2 or state["round_number"] % 2 != 0:
        return {"lint_warnings": []}

    warnings = []
    wiki = state["shadow_wiki"]
    active_files = state["active_files"]

    # Check for broken relative links
    link_pattern = re.compile(r"\[([^\]]+)\]\(\./([^)]+)\)")
    for filename, content in wiki.items():
        for match in link_pattern.finditer(content):
            linked_file = match.group(2).split("#")[0]
            if linked_file not in wiki:
                warnings.append(
                    f"Broken link in {filename}: references '{linked_file}' which does not exist"
                )

    # Check for empty sections (headers with no content beneath)
    for filename, content in wiki.items():
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("## ") and i + 1 < len(lines):
                next_non_empty = ""
                for j in range(i + 1, min(i + 3, len(lines))):
                    if lines[j].strip():
                        next_non_empty = lines[j].strip()
                        break
                if not next_non_empty or next_non_empty.startswith("## ") or next_non_empty.startswith("# "):
                    section_name = line.strip("# ").strip()
                    warnings.append(
                        f"Empty section in {filename}: '{section_name}' has no content"
                    )

    # Use LLM to check for contradictions if we have substantial content
    total_content = sum(len(c) for c in wiki.values())
    if total_content > 500:
        llm = get_llm(HAIKU_MODEL)
        wiki_text = ""
        for fname, content in wiki.items():
            wiki_text += f"\n--- {fname} ---\n{content}\n"

        response = llm.invoke([
            {"role": "system", "content": (
                "You are a specification linter. Scan the following wiki files for "
                "contradictions between files (e.g., one file says Postgres, another says NoSQL), "
                "orphaned concepts (mentioned but never defined), and missing cross-references. "
                "Return a JSON array of warning strings. If no issues found, return an empty array. "
                "Respond with valid JSON only."
            )},
            {"role": "user", "content": wiki_text},
        ])

        content = response.content
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        try:
            llm_warnings = json.loads(content)
            if isinstance(llm_warnings, list):
                warnings.extend(llm_warnings)
        except (json.JSONDecodeError, TypeError):
            pass

    return {"lint_warnings": warnings}
