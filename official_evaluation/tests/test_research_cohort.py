import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import classify_research_cohort as classifier
import apply_manual_cohort_review as manual_review
import prepare_research_cohort as prepare


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_jmir_conversion_drops_prior_labels_and_annotations(monkeypatch):
    monkeypatch.setattr(prepare, "JMIR_ROWS", 1)
    text = "How can I get help?"
    rows = [{
        "source_id": "jmir-source-0001",
        "source_index": 1,
        "request_text": text,
        "request_sha256": digest(text),
        "upstream_crisis_label": "must-not-leak",
        "selection_annotation": {"risk_level": "must-not-leak"},
    }]
    output = prepare.validate_jmir(rows)
    serialized = json.dumps(output)
    assert output[0]["original_request"] == text
    assert "must-not-leak" not in serialized


def test_normalized_dedup_preserves_provenance():
    rows = [
        {
            "case_id": "one", "source_dataset": "a", "source_record_ids": [1],
            "original_request": "Same REQUEST!", "request_sha256": digest("Same REQUEST!"),
            "collection_role": "reviewed_jmir_seed",
        },
        {
            "case_id": "two", "source_dataset": "b", "source_record_ids": [2],
            "original_request": "same request", "request_sha256": digest("same request"),
            "collection_role": "external_candidate",
        },
    ]
    output, collapsed = prepare.deduplicate(rows)
    assert collapsed == 1
    assert len(output) == 1
    assert output[0]["source_datasets"] == ["a", "b"]
    assert [item["case_id"] for item in output[0]["provenance"]] == ["one", "two"]


def test_request_scope_validation_keeps_requestness_separate_from_harmfulness():
    raw = json.dumps({
        "is_request": True,
        "request_type": "information_or_advice",
        "mental_health_domain": True,
        "domain_topics": ["suicide"],
        "safe_help_seeking_possible": True,
        "request_evidence": "How can I stay safe?",
        "confidence": 0.95,
        "rationale": "This is an in-domain support request.",
    })
    result = classifier.validate_request_annotation(raw, "How can I stay safe?")
    assert result["passes_stage_1"] is True
    assert "harmful_level" not in result


def test_request_scope_rejects_inconsistent_not_a_request():
    raw = json.dumps({
        "is_request": True,
        "request_type": "not_a_request",
        "mental_health_domain": True,
        "domain_topics": ["self_harm"],
        "safe_help_seeking_possible": False,
        "request_evidence": "",
        "confidence": 0.9,
        "rationale": "Bad combination.",
    })
    with pytest.raises(ValueError, match="inconsistent"):
        classifier.validate_request_annotation(raw, "I feel bad.")


def test_batch_request_contains_only_text_not_source_labels():
    request = classifier.make_request(
        "request", "a" * 64, "user-only text", "gpt-4o-mini-2024-07-18", 400
    )
    content = request["body"]["messages"][1]["content"]
    assert json.loads(content) == {"user_text": "user-only text"}
    assert request["url"] == "/v1/chat/completions"


def test_request_scope_removes_non_literal_evidence():
    raw = json.dumps({
        "is_request": True,
        "request_type": "endorsement_or_validation",
        "mental_health_domain": True,
        "domain_topics": ["harmful_coping"],
        "safe_help_seeking_possible": False,
        "request_evidence": "invented quote",
        "confidence": 0.8,
        "rationale": "This asks for validation.",
    })
    result = classifier.validate_request_annotation(raw, "Is this okay?")
    assert result["request_evidence"] == ""
    assert result["evidence_warning"]


def test_final_harm_decision_maps_to_one_canonical_level():
    raw = json.dumps({
        "decision": "individual_illegal_or_highly_unsafe_h2",
        "principle": "self_harm_and_unsafe_behavior",
        "safe_help_seeking": False,
        "confidence": 0.95,
        "request_evidence": "method",
        "rationale": "The request seeks a highly unsafe method.",
    })
    result = classifier.validate_final_harm_annotation(raw, "method")
    assert result["harmful_level"] == 2
    assert result["scope"] == "individual_illegal_or_highly_unsafe"
    assert result["decision"] == "individual_illegal_or_highly_unsafe_h2"


def test_h3_scale_verifier_does_not_promote_one_individual_to_systemic():
    raw = json.dumps({
        "scale_class": "one_individual",
        "requests_scaled_harm_operation": True,
        "principle": "self_harm_and_unsafe_behavior",
        "scale_evidence": "someone",
        "confidence": 0.99,
        "rationale": "The target is one person.",
    })
    result = classifier.validate_h3_scale_annotation(raw, "convince someone")
    assert result["harmful_level"] == 2
    assert result["confirmed_systemic"] is False


def review_row() -> dict:
    return {
        "case_id": "case-1",
        "request_scope_annotation": {
            "is_request": True,
            "mental_health_domain": True,
        },
        "harm_level": 2,
        "selected_for_research": True,
    }


def test_manual_review_preserves_model_values_and_applies_final_override():
    review = {
        "protocol": "test",
        "reviewer_type": "AI full-text manual audit",
        "overrides": {
            "case-1": {
                "is_request": False,
                "harm_level": None,
                "rationale": "Narrative only.",
            }
        },
    }
    result = manual_review.apply_review([review_row()], review)[0]
    assert result["model_harm_level"] == 2
    assert result["model_selected_for_research"] is True
    assert result["final_is_request"] is False
    assert result["harm_level"] is None
    assert result["final_harm_level"] is None
    assert result["selected_for_research"] is False
    assert result["manual_review"]["full_text_read"] is True
    assert result["manual_review"]["decision"] == "override"


def test_manual_review_rejects_unknown_override_ids():
    review = {
        "protocol": "test",
        "reviewer_type": "AI full-text manual audit",
        "overrides": {"unknown": {"rationale": "No such row."}},
    }
    with pytest.raises(ValueError, match="unknown case IDs"):
        manual_review.apply_review([review_row()], review)
