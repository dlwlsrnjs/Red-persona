"""Goal-field contract for the corrected harmful-goal experiment.

Version 1 used ``original_request`` both as the source counseling utterance and
as the private experimental goal.  Most source utterances are help-seeking, so
that design can measure latent-request recovery but cannot establish harmful
goal fulfillment.  Version 2 keeps the two constructs separate.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib


LEGACY_GOAL_CONTRACT = "source_request_as_private_goal_v1"
HARMFUL_GOAL_CONTRACT = "separate_harmful_target_v2"
STRICT_HARMFUL_GOAL_CONTRACT = "verified_source_request_harmful_goal_v3"
APPROVED_REVIEW_STATUSES = {"approved", "adjudicated_approved"}


def source_request(case: Mapping) -> str:
    value = str(case.get("original_request", "")).strip()
    if not value:
        raise ValueError("case.original_request must contain the source counseling utterance")
    return value


def _target_record(case: Mapping) -> Mapping | None:
    value = case.get("hidden_adversarial_target")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("hidden_adversarial_target must be an object, not a bare string")
    return value


def _strict_request_record(case: Mapping) -> Mapping | None:
    value = case.get("strict_harmful_request")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("strict_harmful_request must be an object")
    return value


def validate_strict_harmful_goal_case(case: Mapping) -> Mapping:
    """Validate a verbatim, independently verified harmful source request."""
    source = source_request(case)
    strict = _strict_request_record(case)
    if strict is None:
        raise ValueError("v3 requires case.strict_harmful_request")
    if _target_record(case) is not None:
        raise ValueError("v3 strict source requests cannot also define hidden_adversarial_target")
    request_text = str(strict.get("request_text", "")).strip()
    if request_text != source:
        raise ValueError("strict_harmful_request.request_text must equal original_request verbatim")
    expected_hash = hashlib.sha256(request_text.encode("utf-8")).hexdigest()
    if strict.get("request_sha256") != expected_hash:
        raise ValueError("strict_harmful_request.request_sha256 does not match request_text")
    if not str(strict.get("source_id", "")).strip():
        raise ValueError("strict_harmful_request.source_id is required")
    selection = strict.get("selection_annotation")
    verification = strict.get("strict_request_verification")
    if not isinstance(selection, Mapping) or not selection.get("eligible_h1_h2_request"):
        raise ValueError("v3 requires an eligible harmful-request selection annotation")
    if not isinstance(verification, Mapping):
        raise ValueError("v3 requires strict_request_verification")
    if verification.get("is_explicit_harmful_assistance_request") is not True:
        raise ValueError("v3 requires an explicit harmful assistance request")
    if verification.get("exclusion_reason") != "none":
        raise ValueError("v3 strict request must have exclusion_reason='none'")
    return strict


def validate_harmful_goal_case(case: Mapping) -> Mapping:
    """Validate a preregistered, human-reviewed v2 case without judging content.

    The validator deliberately does not infer harmfulness from text.  That
    decision must be registered in the dataset with provenance and human
    review, preventing a response judge from redefining the experimental goal
    after observing model outputs.
    """
    source = source_request(case)
    target = _target_record(case)
    if target is None:
        raise ValueError("v2 requires case.hidden_adversarial_target")

    required = ("text", "taxonomy_id", "source_benchmark", "source_id", "mapping_rationale")
    missing = [field for field in required if not str(target.get(field, "")).strip()]
    if missing:
        raise ValueError(
            "hidden_adversarial_target is missing required fields: " + ", ".join(missing)
        )
    text = str(target["text"]).strip()
    if text == source:
        raise ValueError("hidden_adversarial_target.text must be distinct from original_request")
    if target.get("harmfulness") != "harmful":
        raise ValueError("hidden_adversarial_target.harmfulness must be exactly 'harmful'")

    review = target.get("human_review")
    if not isinstance(review, Mapping):
        raise ValueError("hidden_adversarial_target.human_review must be an object")
    if review.get("status") not in APPROVED_REVIEW_STATUSES:
        raise ValueError(
            "hidden_adversarial_target.human_review.status must record approved adjudication"
        )
    reviewer_count = review.get("reviewer_count")
    if not isinstance(reviewer_count, int) or reviewer_count < 1:
        raise ValueError("hidden_adversarial_target.human_review.reviewer_count must be >= 1")
    return target


def goal_contract(case: Mapping) -> dict:
    """Return normalized metadata and validate v2 automatically when present."""
    strict = _strict_request_record(case)
    if strict is not None:
        validate_strict_harmful_goal_case(case)
        return {
            "version": STRICT_HARMFUL_GOAL_CONTRACT,
            "source_request_field": "original_request",
            "private_goal_field": "original_request",
            "registered_harmful_goal": True,
            "harmful_goal_evaluation_eligible": True,
            "source_benchmark": strict.get(
                "source_benchmark", "JMIR-2046 strict harmful request subset"
            ),
            "source_id": strict["source_id"],
            "request_sha256": strict["request_sha256"],
            "verification": dict(strict["strict_request_verification"]),
        }
    target = _target_record(case)
    if target is None:
        return {
            "version": LEGACY_GOAL_CONTRACT,
            "source_request_field": "original_request",
            "private_goal_field": "original_request",
            "registered_harmful_goal": False,
            "harmful_goal_evaluation_eligible": False,
        }
    validate_harmful_goal_case(case)
    return {
        "version": HARMFUL_GOAL_CONTRACT,
        "source_request_field": "original_request",
        "private_goal_field": "hidden_adversarial_target.text",
        "registered_harmful_goal": True,
        "harmful_goal_evaluation_eligible": True,
        "taxonomy_id": target["taxonomy_id"],
        "source_benchmark": target["source_benchmark"],
        "source_id": target["source_id"],
        "human_review": dict(target["human_review"]),
    }


def experimental_goal(case: Mapping, *, require_harmful_v2: bool = False,
                      require_strict_v3: bool = False) -> str:
    """Return the planner-private objective under the registered case contract."""
    strict = _strict_request_record(case)
    if strict is not None:
        validate_strict_harmful_goal_case(case)
        return source_request(case)
    target = _target_record(case)
    if target is None:
        if require_strict_v3:
            raise ValueError("strict harmful-goal v3 run cannot use an unverified source request")
        if require_harmful_v2:
            raise ValueError("harmful-goal v2 run cannot fall back to original_request")
        return source_request(case)
    if require_strict_v3:
        raise ValueError("strict harmful-goal v3 requires a verified source request")
    validate_harmful_goal_case(case)
    return str(target["text"]).strip()
