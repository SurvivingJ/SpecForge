import json
import os

from graph.state import ProjectState
from config import get_llm, HAIKU_MODEL, DEPTH_CONFIG

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "structure.txt")

WIKI_SKELETONS = {
    "overview.md": """# {project_name} — Overview

## Vision

## Problem Statement

## Target Users

## Constraints and Non-Goals

## Active Specification Files
{file_links}
""",
    "software.md": """# Software Architecture

## Stack Overview

## System Architecture Diagram (described)

## API Design

## Database Schema

## Authentication and Authorisation

## Infrastructure and Deployment

## Key Technical Risks

→ See also: [Design](./design.md#component-hierarchy), [Overview](./overview.md)
""",
    "design.md": """# Design System

## User Personas

## Core User Journeys

## Information Architecture

## Component Hierarchy

## Visual Language (colours, typography, tone)

## Accessibility Requirements

→ See also: [Software](./software.md#api-design), [Overview](./overview.md)
""",
    "business.md": """# Business Model

## Market Context

## User Personas vs. Paying Customers

## Monetisation Strategy

## Competitive Landscape

## Go-to-Market Strategy

## Success Metrics

## Risks

→ See also: [Overview](./overview.md)
""",
    "hardware.md": """# Hardware Specification

## Physical Components

## Sensors and Actuators

## Power Budget

## Communication Protocols

## Manufacturing Constraints

→ See also: [Software](./software.md#infrastructure-and-deployment)
""",
    "world.md": """# World / Narrative Bible

## Setting and Tone

## Characters and Factions

## Rules of the World

## Thematic Intent

## Relationship to Mechanics (if game)

→ See also: [Overview](./overview.md)
""",
    "misc.md": """# Miscellaneous

## Open Questions

## Unresolved Ideas

## Linter Flags
""",
}


def _build_file_links(active_files: list[str]) -> str:
    name_map = {
        "software.md": "Software Architecture",
        "design.md": "Design System",
        "business.md": "Business Model",
        "hardware.md": "Hardware Specification",
        "world.md": "World / Narrative Bible",
        "misc.md": "Miscellaneous",
    }
    lines = []
    for f in active_files:
        if f != "overview.md" and f in name_map:
            lines.append(f"- [{name_map[f]}](./{f})")
    return "\n".join(lines)


def structure_agent(state: ProjectState) -> dict:
    with open(PROMPT_PATH, "r") as f:
        system_prompt = f.read()

    llm = get_llm(HAIKU_MODEL)
    response = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Idea: {state['idea_description']}\nDepth: {state['depth']}"},
    ])

    content = response.content
    # Parse JSON from response (handle markdown code blocks)
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    result = json.loads(content)

    active_files = result["active_files"]
    active_agents = result["active_agents"]
    project_name = result.get("project_name", "Untitled Project")

    # Ensure overview.md and misc.md are always present
    if "overview.md" not in active_files:
        active_files.insert(0, "overview.md")
    if "misc.md" not in active_files:
        active_files.append("misc.md")

    # Build skeleton wiki
    file_links = _build_file_links(active_files)
    shadow_wiki = {}
    for f in active_files:
        if f in WIKI_SKELETONS:
            skeleton = WIKI_SKELETONS[f]
            if f == "overview.md":
                skeleton = skeleton.format(project_name=project_name, file_links=file_links)
            shadow_wiki[f] = skeleton

    # Compute depth quota
    depth_cfg = DEPTH_CONFIG.get(state["depth"], DEPTH_CONFIG["medium"])
    depth_quota = depth_cfg["total_rounds"]

    return {
        "shadow_wiki": shadow_wiki,
        "active_files": active_files,
        "active_agents": active_agents,
        "round_number": 1,
        "depth_quota_remaining": depth_quota,
        "current_questions": [],
        "pending_answers": [],
        "lint_warnings": [],
    }
