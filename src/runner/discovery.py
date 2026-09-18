"""Closed structural snapshot and AI candidate contracts; no page text or values."""
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .workbook_schema import Strict, WorkbookPlan, WorkbookStep

CandidateID = Annotated[str, Field(pattern=r"^c[1-9][0-9]{0,3}$")]
StructuralCSS = Annotated[str, Field(max_length=2000, pattern=
    r"^(?:html|body|div|span|form|section|main|header|footer|nav|article|aside|ul|ol|li|table|thead|tbody|tfoot|tr|td|th|label|fieldset|legend|p|a|button|input|textarea|select|option|h1|h2|h3|h4|h5|h6):nth-of-type\([1-9][0-9]{0,5}\)(?: > (?:html|body|div|span|form|section|main|header|footer|nav|article|aside|ul|ol|li|table|thead|tbody|tfoot|tr|td|th|label|fieldset|legend|p|a|button|input|textarea|select|option|h1|h2|h3|h4|h5|h6):nth-of-type\([1-9][0-9]{0,5}\)){0,39}$")]


class Candidate(Strict):
    id: CandidateID
    selector: StructuralCSS
    kind: Literal["input", "textarea", "select", "button", "a"]

    @model_validator(mode="after")
    def tag_matches(self):
        if self.selector.split(" > ")[-1].split(":")[0] != self.kind:
            raise ValueError("Candidate tag mismatch")
        return self


class Snapshot(Strict):
    schema_version: Literal[1] = 1
    candidates: list[Candidate] = Field(min_length=1, max_length=100)
    truncated: bool = False

    @model_validator(mode="after")
    def unique(self):
        for field in ("id", "selector"):
            values = [getattr(c, field) for c in self.candidates]
            if len(values) != len(set(values)):
                raise ValueError("Duplicate candidate")
        return self

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()


class BoundStep(WorkbookStep):
    candidate_id: CandidateID


class DiscoveryPlan(Strict):
    steps: list[BoundStep] = Field(min_length=1, max_length=100)

    def bind(self, snapshot):
        # Keep the same workbook reference and column checks as Describe.
        rows = [step.model_dump(exclude={"candidate_id"}) for step in self.steps]
        WorkbookPlan.model_validate({"steps": rows})
        if len({step.screen for step in self.steps}) != 1:
            raise ValueError("A snapshot represents one screen")
        candidates = {c.id: c for c in snapshot.candidates}
        for step, row in zip(self.steps, rows):
            if step.group:
                raise ValueError("Structural discovery cannot infer repeated indexed locators")
            candidate = candidates.get(step.candidate_id)
            if candidate is None or not compatible(step.action, candidate.kind, step.read_method):
                raise ValueError("Unknown or incompatible candidate")
            row["locator"] = candidate.selector
            if step.action == "wait":
                row["wait_selector"] = candidate.selector
        return rows


def compatible(action, kind, read_method=""):
    if action in {"fill", "force_fill", "fill_enter"}:
        return kind in {"input", "textarea"}
    if action == "select":
        return kind == "select"
    if action in {"click", "click_if_exists", "wait"}:
        return True
    if action == "read_result_single":
        return read_method in {"css_input", "css_disabled"} and kind in {"input", "textarea", "select"}
    return False


class RepairChoice(Strict):
    candidate_id: CandidateID
    reason: Literal["USER_IDENTIFIED_TARGET", "ACTION_COMPATIBLE_CANDIDATE"]


class RepairProposal(RepairChoice):
    snapshot_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    action: Literal["fill", "force_fill", "fill_enter", "select", "click", "click_if_exists", "read_result_single"]
    read_method: Literal["", "css_input", "css_disabled"] = ""


def repair_proposal(choice, snapshot, action, read_method=""):
    candidate = next((c for c in snapshot.candidates if c.id == choice.candidate_id), None)
    if candidate is None or not compatible(action, candidate.kind, read_method):
        raise ValueError("Unknown or incompatible candidate")
    return RepairProposal(**choice.model_dump(), snapshot_sha256=snapshot.fingerprint(),
                          action=action, read_method=read_method)
