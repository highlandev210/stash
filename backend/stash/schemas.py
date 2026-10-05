from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Status = Literal["backlog", "ready", "in_progress", "blocked", "done", "cancelled"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(Strict):
    name: str = Field(default="You", min_length=1, max_length=100)
    kind: Literal["human", "agent"] = "human"


class Mutation(Strict):
    actor: Actor = Field(default_factory=Actor)


class Registration(Mutation):
    path: str = Field(min_length=1, max_length=4096)


class SettingsPatch(Mutation):
    revision: int = Field(ge=0)
    master_folder: str = ""
    identity: str = Field(default="You", min_length=1, max_length=100)


class ProjectPatch(Mutation):
    revision: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    path: str
    status: Literal["active", "paused", "archived"] = "active"
    description: str = Field(default="", max_length=10000)
    purpose: str = Field(default="", max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    stack: list[str] = Field(default_factory=list, max_length=100)
    focus: str = Field(default="", max_length=20000)
    next_step: str = Field(default="", max_length=20000)
    brief: str = Field(default="", max_length=50000)
    setup_command: str = Field(default="", max_length=10000)
    run_command: str = Field(default="", max_length=10000)
    test_command: str = Field(default="", max_length=10000)
    services: list[str] = Field(default_factory=list, max_length=100)
    env_names: list[str] = Field(default_factory=list, max_length=100)
    repo_url: str = Field(default="", max_length=4096)
    demo_url: str = Field(default="", max_length=4096)
    screenshot: str = Field(default="", max_length=4096)
    doc_roots: list[str] = Field(default_factory=lambda: ["README.md", "docs", ".stash/docs", ".stash/decisions", ".stash/handoffs"], max_length=20)
    writable_doc_roots: list[str] = Field(default_factory=lambda: ["docs", ".stash/docs"], max_length=20)

    @model_validator(mode="after")
    def writable_is_readable(self):
        from pathlib import PurePosixPath
        for raw in self.writable_doc_roots:
            target = PurePosixPath(raw)
            if not any(target == PurePosixPath(root) or PurePosixPath(root) in target.parents for root in self.doc_roots):
                raise ValueError("Writable document paths must be within readable document paths")
        return self

    @field_validator("repo_url", "demo_url")
    @classmethod
    def web_url(cls, value):
        from urllib.parse import urlsplit
        if value and (urlsplit(value).scheme not in {"http", "https"} or not urlsplit(value).netloc):
            raise ValueError("Use an http(s) URL")
        return value

    @field_validator("env_names")
    @classmethod
    def names_only(cls, value):
        import re
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item) for item in value):
            raise ValueError("Store environment variable names only, without values")
        return value

    @field_validator("doc_roots", "writable_doc_roots", "screenshot")
    @classmethod
    def relative_paths(cls, value):
        from pathlib import PurePosixPath
        for item in ([value] if isinstance(value, str) else value):
            if item and (PurePosixPath(item).is_absolute() or ".." in PurePosixPath(item).parts or "\\" in item):
                raise ValueError("Use project-relative paths without traversal")
        return value


class IssueInput(Mutation):
    title: str = Field(min_length=1, max_length=300)
    type: Literal["bug", "task", "feature"] = "task"
    status: Status = "backlog"
    priority: Literal["low", "medium", "high"] = "medium"
    description: str = Field(default="", max_length=50000)
    acceptance_criteria: str = Field(default="", max_length=20000)
    reproduction_steps: str = Field(default="", max_length=20000)
    expected_behavior: str = Field(default="", max_length=20000)
    actual_behavior: str = Field(default="", max_length=20000)
    affected_version: str = Field(default="", max_length=1000)
    verification: str = Field(default="", max_length=20000)
    labels: list[str] = Field(default_factory=list, max_length=100)
    links: list[str] = Field(default_factory=list, max_length=100)


class IssuePatch(IssueInput):
    revision: str = Field(min_length=1, max_length=64)


class Decision(Mutation):
    choice: str = Field(min_length=1, max_length=10000)
    reasoning: str = Field(default="", max_length=20000)
    alternatives: str = Field(default="", max_length=20000)
    reference: str = Field(default="", max_length=1000)


class Handoff(Mutation):
    summary: str = Field(min_length=1, max_length=10000)
    completed_work: str = Field(default="", max_length=30000)
    changed_files: str = Field(default="", max_length=20000)
    verification: str = Field(default="", max_length=30000)
    unresolved_problems: str = Field(default="", max_length=20000)
    blockers: str = Field(default="", max_length=20000)
    next_actions: str = Field(min_length=1, max_length=20000)
    commit: str = Field(default="", max_length=1000)


class Comment(Mutation):
    body: str = Field(min_length=1, max_length=20000)


class DocumentWrite(Mutation):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=500000)
    revision: str | None = None


class SessionStart(Mutation):
    origin: Literal["explicit", "codex_hook"] = "explicit"
    id: str
    task: str = Field(min_length=1, max_length=10000)


class CheckpointInput(Mutation):
    id: str
    revision: str = Field(min_length=1, max_length=64)
    progress: str = Field(default="", max_length=30000)
    blockers: str = Field(default="", max_length=20000)
    unfinished_work: str = Field(default="", max_length=20000)
    next_actions: str = Field(min_length=1, max_length=20000)
    verification: str = Field(default="", max_length=30000)
    verification_includes_uncommitted: bool | None = None
    final: bool = False


class SessionTask(Mutation):
    revision: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=10000)


class HookObservation(Mutation):
    id: str
    session_id: str
    runtime_key: str = Field(pattern=r'^[0-9a-f]{64}$')
    event: Literal['SessionStart', 'PostToolUse', 'Stop', 'Interrupt', 'SessionEnd']
    observed_at: str
    turn_key: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    tool_call_key: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    tool: Literal['shell', 'edit', 'mcp', 'other'] | None = None
    exit_code: int | None = Field(default=None, ge=-65535, le=65535)
    tool_error: bool | None = None
    source: Literal['startup', 'resume', 'clear', 'compact'] | None = None


class WatcherConfig(Mutation):
    enabled: bool


class AssessmentRequest(Mutation):
    mode: Literal['new', 'existing'] = 'existing'
    goal: str = Field(default='', max_length=20000)
    requirements: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(default_factory=list, max_length=100)
    run_checks: list[str] = Field(default_factory=list, max_length=10)


class AssessmentApproval(Mutation):
    revision: str = Field(min_length=1, max_length=64)
    fields: list[str] = Field(default_factory=list, max_length=20)
    candidates: list[str] = Field(default_factory=list, max_length=400)
    enable_watcher: bool = True


class ProjectCreation(Mutation):
    path: str = Field(min_length=1, max_length=4096)


class AssessmentFinding(Strict):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10000)
    evidence: list[str] = Field(min_length=1, max_length=20)
    type: Literal['bug', 'task', 'feature'] = 'task'
    confidence: Literal['observed', 'inferred', 'needs_review'] = 'inferred'


class AssessmentRefinement(Mutation):
    revision: str = Field(min_length=1, max_length=64)
    proposed: dict[str, str | list[str]] = Field(default_factory=dict, max_length=20)
    findings: list[AssessmentFinding] = Field(default_factory=list, max_length=80)
    analysis: str = Field(default='', max_length=30000)
