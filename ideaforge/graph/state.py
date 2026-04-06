from typing import TypedDict, Annotated
import operator


class ProjectState(TypedDict):
    # Input
    idea_description: str
    depth: str  # 'shallow' | 'medium' | 'deep' | 'abyss'

    # Shadow Wiki
    shadow_wiki: dict[str, str]  # {"overview.md": "# Overview\n...", ...}
    active_files: list[str]

    # Q&A Cycle
    current_questions: list[dict]  # [{id, text, type, target_file, agent}]
    pending_answers: list[dict]  # [{question_id, answer}]
    question_history: Annotated[list, operator.add]  # Accumulates all rounds

    # Control Flow
    round_number: int
    depth_quota_remaining: int  # Decrements each round; 0 triggers completion
    is_complete: bool

    # Active Agents
    active_agents: list[str]  # Determined by Structure Agent on init

    # Linting
    lint_warnings: list[str]
