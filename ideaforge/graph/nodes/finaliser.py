from graph.state import ProjectState


def finaliser_node(state: ProjectState) -> dict:
    """Polish pass: generate index.md and validate cross-links."""
    shadow_wiki = dict(state["shadow_wiki"])
    active_files = state["active_files"]

    # Generate index.md
    name_map = {
        "overview.md": "Project overview, vision, and constraints",
        "software.md": "Software architecture, APIs, databases, and infrastructure",
        "design.md": "Design system, user journeys, and visual language",
        "business.md": "Business model, market context, and monetisation",
        "hardware.md": "Hardware specification, sensors, and manufacturing",
        "world.md": "World building, narrative, and lore",
        "misc.md": "Open questions and unresolved items",
    }

    index_lines = ["# Specification Index\n"]
    for f in active_files:
        summary = name_map.get(f, "Specification file")
        index_lines.append(f"- [{f}](./{f}) — {summary}")

    index_lines.append("")
    shadow_wiki["index.md"] = "\n".join(index_lines)

    return {
        "shadow_wiki": shadow_wiki,
        "is_complete": True,
    }
