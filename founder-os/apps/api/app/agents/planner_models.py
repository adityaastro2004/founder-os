"""
Founder OS — Planner Output Models
====================================
Structured Pydantic models for the Weekly Planner output.

Provides:
  - WeeklyPlan (root model with priorities, daily schedule, delegations, etc.)
  - parse_plan_to_model() — LLM post-processor that converts markdown → JSON
  - plan_to_ical() — generates .ics calendar data from a plan
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"


# ============================================================================
# Sub-models
# ============================================================================

class ICEScore(BaseModel):
    """Impact × Confidence × Ease scoring."""
    impact: int = Field(5, ge=1, le=10, description="How much does this move the needle?")
    confidence: int = Field(5, ge=1, le=10, description="How sure are we this will work?")
    ease: int = Field(5, ge=1, le=10, description="How quickly can we execute?")

    @property
    def total(self) -> float:
        return round((self.impact * self.confidence * self.ease) / 10, 1)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        d = super().model_dump(**kwargs)
        d["total"] = self.total
        return d


class PlanTask(BaseModel):
    """A single actionable task within the daily schedule."""
    id: str = Field(default_factory=lambda: f"pt-{uuid.uuid4().hex[:8]}")
    title: str
    description: str = ""
    owner_agent: str = "planner"
    priority: int = Field(5, ge=1, le=10, description="1=urgent, 10=backlog")
    est_hours: float = Field(1.0, ge=0.25, le=8.0)
    start_time: Optional[str] = Field(None, description="HH:MM format, e.g. '09:00'")
    end_time: Optional[str] = Field(None, description="HH:MM format, e.g. '11:00'")
    status: TaskStatus = TaskStatus.PENDING
    ice_score: ICEScore = Field(default_factory=ICEScore)
    tags: list[str] = Field(default_factory=list)


class Priority(BaseModel):
    """A top-level priority for the week."""
    rank: int = Field(ge=1, le=5)
    title: str
    rationale: str = ""
    ice_score: ICEScore = Field(default_factory=ICEScore)
    owner_agent: str = "planner"


class DaySchedule(BaseModel):
    """Schedule for a single day."""
    day: DayOfWeek
    date: Optional[date] = None
    tasks: list[PlanTask] = Field(default_factory=list)
    notes: str = ""

    @property
    def total_hours(self) -> float:
        return sum(t.est_hours for t in self.tasks)


class Delegation(BaseModel):
    """A task delegated to a specialist agent."""
    agent: str
    task: str
    deadline: str = ""
    priority: int = Field(5, ge=1, le=10)


class Risk(BaseModel):
    """A risk and its mitigation strategy."""
    risk: str
    mitigation: str
    severity: str = "medium"  # low, medium, high


# ============================================================================
# Root Model
# ============================================================================

class WeeklyPlan(BaseModel):
    """Complete structured output from the Weekly Planner."""
    id: str = Field(default_factory=lambda: f"wp-{uuid.uuid4().hex[:8]}")
    week_of: date = Field(default_factory=lambda: _next_monday())
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    # Core plan sections
    top_priorities: list[Priority] = Field(default_factory=list)
    daily_schedule: dict[str, DaySchedule] = Field(default_factory=dict)
    delegations: list[Delegation] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)

    # Metadata
    source_markdown: str = Field("", description="Original markdown plan from LLM")
    founder_context: dict[str, Any] = Field(default_factory=dict)
    total_planned_hours: float = 0.0

    def compute_totals(self) -> None:
        """Compute derived fields."""
        self.total_planned_hours = sum(
            day.total_hours for day in self.daily_schedule.values()
        )

    def ensure_daily_schedule(self) -> None:
        """
        If daily_schedule is empty but we have priorities, auto-distribute
        them across the week as concrete tasks with time slots.
        This ensures calendar events are always created.
        """
        if self.daily_schedule:
            return  # already has tasks

        if not self.top_priorities:
            return  # nothing to distribute

        days = list(DayOfWeek)
        next_mon = _next_monday()

        # Create a schedule with each priority broken into daily tasks
        for i, day_enum in enumerate(days):
            day_date = next_mon + timedelta(days=i)
            tasks: list[PlanTask] = []

            # Distribute priorities round-robin across days
            for j, priority in enumerate(self.top_priorities):
                if j % len(days) == i or len(self.top_priorities) <= len(days):
                    # Each priority gets a 2-hour block
                    hour = 9 + len(tasks) * 2
                    if hour >= 18:
                        break
                    tasks.append(PlanTask(
                        title=priority.title,
                        description=priority.rationale,
                        owner_agent=priority.owner_agent,
                        priority=priority.rank,
                        est_hours=2.0,
                        start_time=f"{hour:02d}:00",
                        end_time=f"{hour + 2:02d}:00",
                        ice_score=priority.ice_score,
                        tags=["auto-scheduled"],
                    ))

            if not tasks and self.top_priorities:
                # Ensure at least one task per day from the first priority
                p = self.top_priorities[min(i, len(self.top_priorities) - 1)]
                tasks.append(PlanTask(
                    title=f"{p.title} (continued)",
                    description=p.rationale,
                    owner_agent=p.owner_agent,
                    priority=p.rank,
                    est_hours=2.0,
                    start_time="09:00",
                    end_time="11:00",
                    ice_score=p.ice_score,
                    tags=["auto-scheduled"],
                ))

            self.daily_schedule[day_enum.value] = DaySchedule(
                day=day_enum,
                tasks=tasks,
            )

        self.compute_totals()


def _next_monday() -> date:
    """Return the date of the upcoming Monday."""
    today = date.today()
    days_ahead = 0 - today.weekday()  # Monday = 0
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


# ============================================================================
# LLM Post-Processor: Markdown → WeeklyPlan
# ============================================================================

PARSE_SYSTEM_PROMPT = """\
You are a strict JSON data extractor. Given a markdown weekly plan, extract the \
information into the exact JSON schema provided. Be thorough — capture every \
task, priority, delegation, and risk mentioned.

CRITICAL: Return ONLY valid, parseable JSON. Do NOT wrap it in ```json blocks. \
Do NOT include any markdown, headers, or conversational text. Start directly with {."""

PARSE_USER_TEMPLATE = """\
Extract the following weekly plan into this JSON schema:

{schema}

---

WEEKLY PLAN TO EXTRACT:

{markdown_plan}

---

RULES for extraction:
- Output MUST be valid JSON matching the schema precisely.
- For each task in the daily schedule, infer start_time and end_time from context \
  (use business hours 09:00–18:00 if not explicitly stated).
- Map owner_agent strictly to one of: planner, content, research, ops, product, support.
- For ICE scores, infer from context if not explicit (default: impact=5, confidence=5, ease=5).
- priority: 1=most urgent, 10=backlog
- Include ALL tasks mentioned, don't skip any.
- Dates should be for the upcoming week starting {next_monday}.
"""


async def parse_plan_to_model(
    markdown_plan: str,
    llm_provider: Any,
    model: str | None = None,
) -> WeeklyPlan:
    """
    Use a second LLM call to convert a markdown plan into a WeeklyPlan model.

    Falls back to a minimal plan if parsing fails.
    """
    from app.agents.llm import LLMMessage, Role

    schema = WeeklyPlan.model_json_schema()
    next_mon = _next_monday().isoformat()

    user_msg = PARSE_USER_TEMPLATE.format(
        schema=json.dumps(schema, indent=2),
        markdown_plan=markdown_plan,
        next_monday=next_mon,
    )

    messages = [LLMMessage(role=Role.USER, content=user_msg)]

    try:
        response = await llm_provider.generate(
            messages,
            system=PARSE_SYSTEM_PROMPT,
            model=model,
            temperature=0.1,  # deterministic extraction
            max_tokens=4096,
        )

        # Clean response — strip markdown fences if present
        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        # Fix common LLM JSON errors
        raw = _clean_llm_json(raw)

        data = json.loads(raw)
        plan = WeeklyPlan.model_validate(data)
        plan.source_markdown = markdown_plan
        plan.ensure_daily_schedule()
        plan.compute_totals()
        return plan

    except json.JSONDecodeError as jde:
        # Second chance: ask the LLM to fix the JSON
        try:
            repair_msg = LLMMessage(
                role=Role.USER,
                content=(
                    f"The following JSON has a syntax error at character {jde.pos}. "
                    f"Fix it and return ONLY valid JSON, nothing else:\n\n{raw}"
                ),
            )
            repair_resp = await llm_provider.generate(
                [repair_msg],
                system="You fix broken JSON. Return ONLY the corrected JSON.",
                model=model,
                temperature=0.0,
                max_tokens=4096,
            )
            fixed = repair_resp.content.strip()
            fixed = re.sub(r"^```(?:json)?\s*", "", fixed)
            fixed = re.sub(r"\s*```$", "", fixed)
            fixed = _clean_llm_json(fixed)
            data = json.loads(fixed)
            plan = WeeklyPlan.model_validate(data)
            plan.source_markdown = markdown_plan
            plan.ensure_daily_schedule()
            plan.compute_totals()
            return plan
        except Exception as repair_exc:
            jde = Exception(f"{jde} | Repair failed: {repair_exc}")

        return WeeklyPlan(
            source_markdown=markdown_plan,
            top_priorities=[
                Priority(rank=1, title="Parse Failed (Repair Failed)"),
            ],
            success_criteria=[f"Parse failed: {jde}"],
        )
    # ↑ ensure_daily_schedule not needed here — "Parse Failed" title
    # is not a useful calendar event

    except Exception as exc:
        # Fallback: return a minimal plan with the raw markdown
        plan = WeeklyPlan(
            source_markdown=markdown_plan,
            top_priorities=[
                Priority(rank=1, title="Parse Failed (Generation Error)"),
            ],
            success_criteria=[f"Parse failed: {exc}"],
        )
        plan.ensure_daily_schedule()
        return plan


def _clean_llm_json(raw: str) -> str:
    """
    Fix common JSON issues from LLM output:
    - Trailing commas before } or ]
    - JavaScript-style comments (// and /* */)
    - Single-quoted strings
    - Unquoted property names
    - Ellipsis placeholders
    """
    # Remove single-line comments (// ...)
    raw = re.sub(r'//[^\n]*', '', raw)
    # Remove multi-line comments (/* ... */)
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    # Remove ... or "..." placeholder entries (e.g., "tuesday": { ... })
    raw = re.sub(r'"[a-z]+":\s*\{\s*\.\.\.\s*\},?', '', raw)
    raw = re.sub(r'"[a-z]+":\s*"\.\.\.",?', '', raw)
    raw = re.sub(r'\{\s*\.\.\.\s*\},?', '', raw)
    raw = re.sub(r'"\.\.\.",?', '', raw)
    # Remove trailing commas before } or ]
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    return raw


# ============================================================================
# ICS Calendar Export
# ============================================================================

def plan_to_ical(plan: WeeklyPlan, calendar_name: str = "Founder OS") -> str:
    """
    Convert a WeeklyPlan into an .ics (iCalendar) string.

    Each task with a start_time becomes a calendar event.
    Tasks without times become all-day events on their day.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{calendar_name}//Weekly Planner//EN",
        f"X-WR-CALNAME:{calendar_name} — Week of {plan.week_of.isoformat()}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    day_offsets = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4,
    }

    for day_name, schedule in plan.daily_schedule.items():
        day_key = day_name.lower()
        offset = day_offsets.get(day_key, 0)
        task_date = plan.week_of + timedelta(days=offset)

        for task in schedule.tasks:
            uid = f"{task.id}@founder-os"
            now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            summary = _ical_escape(task.title)
            desc_parts = []
            if task.description:
                desc_parts.append(task.description)
            desc_parts.append(f"Agent: {task.owner_agent}")
            desc_parts.append(f"Priority: {task.priority}/10")
            desc_parts.append(f"Est: {task.est_hours}h")
            if task.ice_score:
                desc_parts.append(f"ICE: {task.ice_score.total}")
            description = _ical_escape("\\n".join(desc_parts))

            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{uid}")
            lines.append(f"DTSTAMP:{now_stamp}")
            lines.append(f"SUMMARY:{summary}")
            lines.append(f"DESCRIPTION:{description}")

            if task.start_time and task.end_time:
                # Timed event
                start_dt = datetime.combine(
                    task_date,
                    time.fromisoformat(task.start_time),
                )
                end_dt = datetime.combine(
                    task_date,
                    time.fromisoformat(task.end_time),
                )
                lines.append(f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}")
                lines.append(f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}")
            elif task.start_time:
                # Start time but no end — use est_hours
                start_dt = datetime.combine(
                    task_date,
                    time.fromisoformat(task.start_time),
                )
                end_dt = start_dt + timedelta(hours=task.est_hours)
                lines.append(f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%S')}")
                lines.append(f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%S')}")
            else:
                # All-day event
                lines.append(f"DTSTART;VALUE=DATE:{task_date.strftime('%Y%m%d')}")
                lines.append(
                    f"DTEND;VALUE=DATE:"
                    f"{(task_date + timedelta(days=1)).strftime('%Y%m%d')}"
                )

            # Color-code by agent
            agent_colors = {
                "planner": "5", "content": "3", "research": "9",
                "support": "2",
            }
            color = agent_colors.get(task.owner_agent, "0")
            lines.append(f"COLOR:{color}")
            lines.append(f"CATEGORIES:{task.owner_agent}")

            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def _ical_escape(text: str) -> str:
    """Escape special characters for iCalendar format."""
    text = text.replace("\\", "\\\\")
    text = text.replace(",", "\\,")
    text = text.replace(";", "\\;")
    text = text.replace("\n", "\\n")
    return text
