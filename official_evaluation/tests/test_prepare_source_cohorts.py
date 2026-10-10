import csv
import io
import json
import lzma
from pathlib import Path
import sys

import pytest


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


def test_beavertails_evaluation_selects_prompt_text_only(monkeypatch):
    monkeypatch.setitem(subject.SOURCES["beavertails_evaluation"], "rows", 28)
    monkeypatch.setitem(subject.SOURCES["beavertails_evaluation"], "category_rows", 2)
    monkeypatch.setitem(subject.SOURCES["beavertails_evaluation"], "self_harm_rows", 2)
    rows = []
    for category_id in range(14):
        category = "self_harm" if category_id == 10 else f"category_{category_id}"
        for item in range(2):
            rows.append({
                "prompt": f"{category} prompt {item}",
                "category": category,
                "category_id": category_id,
            })
    payload = lzma.compress(
        ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
    )
    selected, audit = subject.build_beavertails_evaluation(payload)
    assert [row["original_request"] for row in selected] == [
        "self_harm prompt 0", "self_harm prompt 1"
    ]
    assert audit["self_harm_rows"] == 2


def test_mvrcii_discards_assistant_and_labels_and_collapses_text(monkeypatch):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    monkeypatch.setitem(subject.SOURCES["mvrcii_safety_harmful"], "rows", 3)
    monkeypatch.setitem(subject.SOURCES["mvrcii_safety_harmful"], "candidate_rows", 2)
    message = pa.struct([("role", pa.string()), ("content", pa.string())])
    metadata = {b"huggingface": json.dumps({"info": {"features": {
        "topic": {"names": ["other", "self_harm_suicide"]}
    }}}).encode()}
    schema = pa.schema([
        ("text", pa.list_(message)), ("topic", pa.int64()),
        ("source", pa.string()), ("label", pa.int64()),
    ], metadata=metadata)
    table = pa.Table.from_pylist([
        {"text": [{"role": "user", "content": "same user text"},
                  {"role": "assistant", "content": "must be discarded"}],
         "topic": 1, "source": "one", "label": 2},
        {"text": [{"role": "user", "content": "same user text"},
                  {"role": "assistant", "content": "different response"}],
         "topic": 1, "source": "two", "label": 0},
        {"text": [{"role": "user", "content": "other topic"}],
         "topic": 0, "source": "three", "label": 2},
    ], schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    selected, audit = subject.build_mvrcii_text_candidates(sink.getvalue().to_pybytes())
    assert len(selected) == 1
    assert selected[0]["original_request"] == "same user text"
    assert selected[0]["source_row_indices"] == [0, 1]
    assert selected[0]["upstream_sources"] == ["one", "two"]
    assert "must be discarded" not in json.dumps(selected)
    assert audit["duplicate_source_rows_collapsed"] == 1


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
