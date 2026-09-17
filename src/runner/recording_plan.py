"""Biên dịch bằng chứng Recorder sang contract Runner, không chép thao tác mù quáng."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .scoped_locator import decode, PREFIX
from .workbook_schema import Strict, WorkbookStep, WorkbookPlan


class RecordedEvent(Strict):
    id: int = Field(ge=1, le=1000)
    screen: Annotated[str, Field(pattern=r"^recorded(?:_[0-9]{3})?$")]
    action: Literal["click", "fill", "select", "check", "uncheck", "upload", "wait", "read_result_single"]
    locator: str = Field(min_length=1, max_length=2000)
    widget: Literal["native", "antd_select", "antd_option"] = "native"
    related_locator: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def structural(self):
        parts = decode(self.locator)
        tag = parts[-1]["css"].split(" > ")[-1].split(":")[0]
        if self.action == "fill" and tag not in {"input", "textarea"}:
            raise ValueError("Expected fillable control")
        if self.action == "read_result_single" and tag not in {"input", "textarea", "select"}:
            raise ValueError("Expected input result control")
        if self.action in {"upload", "check", "uncheck"} and tag != "input":
            raise ValueError("Expected input control")
        if self.action == "select" and tag != "select":
            raise ValueError("Expected native select")
        if self.widget != "native":
            if self.action != "click":
                raise ValueError("Widget evidence must describe a click")
            if self.widget == "antd_select" and tag != "input":
                raise ValueError("Runner Ant selector requires a fillable input")
            if self.widget == "antd_option":
                target = decode(self.related_locator)[-1]["css"]
                if target.split(" > ")[-1].split(":")[0] != "input":
                    raise ValueError("Missing dropdown trigger")
        if self.widget != "antd_option" and self.related_locator:
            raise ValueError("Unexpected related locator")
        return self


class RecordingTrace(Strict):
    schema_version: Literal[1] = 1
    events: list[RecordedEvent] = Field(min_length=1, max_length=500)
    dropped: int = Field(default=0, ge=0, le=1000000)

    @model_validator(mode="after")
    def ordered(self):
        if [event.id for event in self.events] != list(range(1, len(self.events) + 1)):
            raise ValueError("Recording IDs must be contiguous")
        return self


class RecordedStep(WorkbookStep):
    event_ids: list[Annotated[int, Field(ge=1, le=1000)]] = Field(min_length=1, max_length=500)
    review: Literal["NONE", "REVIEW_LOCATOR", "REVIEW_REPEAT", "REVIEW_CUSTOM_CONTROL"] = "NONE"


class RecordingPlan(Strict):
    steps: list[RecordedStep] = Field(min_length=1, max_length=100)

    def bind(self, trace):
        rows = [step.model_dump(exclude={"event_ids", "review"}) for step in self.steps]
        WorkbookPlan.model_validate({"steps": rows})
        # Every event is accounted for once, preserving order. AI cannot silently drop a click.
        if [eid for step in self.steps for eid in step.event_ids] != [event.id for event in trace.events]:
            raise ValueError("AI must cover every event in order")
        evidence = {event.id: event for event in trace.events}
        notes = []
        for step, row in zip(self.steps, rows):
            events = [evidence[eid] for eid in step.event_ids]
            first = events[0]
            if any(event.screen != step.screen for event in events) or step.group or step.prefill_check != "N":
                raise ValueError("Unproven screen/group/prefill change")
            ant = (len(events) >= 2 and first.widget == "antd_select" and
                   events[-1].widget == "antd_option" and events[-1].related_locator == first.locator and
                   not first.locator.startswith(PREFIX) and
                   all(e.action == "fill" and e.locator == first.locator for e in events[1:-1]))
            if step.action == "select_antd":
                if not ant or step.value_source != "testcase" or step.match_type != "exact" or step.dropdown_selector != "visible":
                    raise ValueError("Insufficient evidence for Runner select_antd")
            else:
                if step.action != first.action or any(e.action != first.action or e.locator != first.locator for e in events):
                    raise ValueError("Action does not match recording")
                if len(events) > 1 and first.action != "fill":
                    raise ValueError("Only consecutive fills on the same target may collapse")
                expected = "testcase" if first.action in {"fill", "select", "upload"} else "empty"
                if step.value_source != expected or step.dropdown_selector:
                    raise ValueError("Unproven value source or dropdown")
                if first.action == "read_result_single" and (step.read_method != "css_input" or step.match_type != "exact"):
                    raise ValueError("Only recorded input reads are proven")
                if first.action != "read_result_single" and step.match_type:
                    raise ValueError("Unexpected match type")
            if step.wait_selector and step.action != "wait":
                raise ValueError("Unrecorded wait")
            row["locator"] = first.locator
            row["wait_selector"] = first.locator if step.action == "wait" else ""
            review = step.review
            if first.widget != "native" and step.action != "select_antd":
                review = "REVIEW_CUSTOM_CONTROL"
            if review == "REVIEW_LOCATOR":
                row["locator"] = ":not(*)"
                if step.action == "wait":
                    row["wait_selector"] = ":not(*)"
            notes.append({"step": step.step, "events": step.event_ids, "review": review})
        return rows, notes
