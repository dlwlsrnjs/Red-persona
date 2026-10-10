import csv
import io
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import prepare_source_cohorts as subject
import annotate_harm_levels as annotator


def test_normalized_request_joins_turn_fragments():
    assert subject.normalized_request([" hello ", "there"]) == "hello there"


def test_jmir_builder_rejects_misaligned_label_rows(monkeypatch):
    monkeypatch.setitem(subject.SOURCES["jmir_inputs"], "rows", 1)
    monkeypatch.setitem(subject.SOURCES["jmir_labels"], "rows", 1)
    source = json.dumps([{"inputs": ["a"], "dataset_id": "reused", "label": ""}]).encode()
    labels = json.dumps([{"inputs": ["b"], "dataset_id": "reused", "all_labels": []}]).encode()
    try:
        subject.build_jmir(source, labels)
    except ValueError as exc:
        assert "not row-aligned" in str(exc)
    else:
        raise AssertionError("misalignment was accepted")


def test_jmir_identity_uses_row_index_even_when_dataset_id_is_reused(monkeypatch):
    monkeypatch.setitem(subject.SOURCES["jmir_inputs"], "rows", 2)
    monkeypatch.setitem(subject.SOURCES["jmir_labels"], "rows", 2)
    rows = [
        {"inputs": ["first"], "dataset_id": "same", "label": ""},
        {"inputs": ["second"], "dataset_id": "same", "label": ""},
    ]
    labels = [{**row, "all_labels": []} for row in rows]
    built, audit = subject.build_jmir(json.dumps(rows).encode(), json.dumps(labels).encode())
    assert [row["case_id"] for row in built] == ["jmir-2046-0000", "jmir-2046-0001"]
    assert audit["unique_source_dataset_ids"] == 1


def test_ailuminate_builder_filters_ssh_without_pooling_other_hazards(monkeypatch):
    monkeypatch.setitem(subject.SOURCES["ailuminate_demo"], "rows", 2)
    monkeypatch.setitem(subject.SOURCES["ailuminate_demo"], "ssh_rows", 1)
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=[
        "release_prompt_id", "prompt_text", "hazard", "persona", "locale", "prompt_hash"
    ])
    writer.writeheader()
    writer.writerow({
        "release_prompt_id": "one", "prompt_text": "ssh prompt", "hazard": "ssh",
        "persona": "skilled", "locale": "en_US", "prompt_hash": "hash-one",
    })
    writer.writerow({
        "release_prompt_id": "two", "prompt_text": "other", "hazard": "vcr",
        "persona": "unskilled", "locale": "en_US", "prompt_hash": "hash-two",
    })
    built, audit = subject.build_ailuminate(handle.getvalue().encode())
    assert len(built) == 1
    assert built[0]["source_release_prompt_id"] == "one"
    assert audit["all_demo_rows"] == 2


def test_harm_level_validation_removes_non_literal_evidence():
    raw = json.dumps({
        "harmful_level": 2,
        "principle": "self_harm_and_unsafe_behavior",
        "scope": "individual_illegal_or_highly_unsafe",
        "safe_help_seeking": False,
        "confidence": 0.9,
        "request_evidence": "invented quote",
        "rationale": "The request seeks actionable harmful assistance.",
    })
    value = annotator.validate_annotation(raw, "actual request")
    assert value["harmful_level"] == 2
    assert value["request_evidence"] == ""
    assert value["evidence_warning"]


def test_harm_level_grouping_reuses_identical_requests_but_keeps_rows():
    request = "same request"
    rows = [
        {"case_id": "one", "original_request": request},
        {"case_id": "two", "original_request": request},
    ]
    grouped = annotator.validate_rows(rows)
    assert len(grouped) == 1
    assert len(next(iter(grouped.values()))) == 2
