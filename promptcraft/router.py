"""Rule-based prompt technique routing."""

from __future__ import annotations

from .classifier import classify_stage_event
from .features import RequestFeatures, extract_features
from .models import PromptRequest, RouteResult, StageEvent, Technique


IN_STAGE_EVENTS = {
    StageEvent.CONTINUE_STAGE,
    StageEvent.REPAIR_CURRENT_STAGE,
    StageEvent.FORMAT_ADJUSTMENT,
}


def route_technique(
    request: PromptRequest, forced_technique: Technique | None = None
) -> RouteResult:
    event, classifier_reasons, needs_confirmation = classify_stage_event(request)
    if event is StageEvent.NEED_USER_INPUT:
        return RouteResult(
            event=event,
            selected=None,
            candidate_pool=[],
            reasons=classifier_reasons,
            needs_confirmation=needs_confirmation,
        )

    features = extract_features(request)
    candidates = candidate_pool_for(event, features)
    if forced_technique is not None:
        selected = forced_technique
        reasons = classifier_reasons + [
            f"User selected skill {forced_technique.value}; automatic routing was bypassed."
        ]
    else:
        selected = select_technique(event, features, candidates)
        reasons = classifier_reasons + _routing_reasons(selected, event, features)
    return RouteResult(
        event=event,
        selected=selected,
        candidate_pool=candidates,
        reasons=reasons,
    )


def candidate_pool_for(event: StageEvent, features: RequestFeatures) -> list[Technique]:
    simple_candidates = [
        Technique.ZERO_SHOT,
        Technique.FEW_SHOT,
        Technique.ZERO_SHOT_COT,
        Technique.FEW_SHOT_COT,
    ]
    advanced_candidates = [
        Technique.STEP_BACK,
        Technique.LEAST_TO_MOST,
        Technique.TREE_OF_THOUGHTS,
    ]

    del features
    if event in IN_STAGE_EVENTS:
        return simple_candidates

    return simple_candidates + advanced_candidates


def select_technique(
    event: StageEvent, features: RequestFeatures, candidates: list[Technique]
) -> Technique:
    if event in IN_STAGE_EVENTS:
        return _select_lightweight(features)
    ordered_preferences = [
        (features.has_reasoning_examples, Technique.FEW_SHOT_COT),
        (features.has_examples, Technique.FEW_SHOT),
        (features.needs_multipath, Technique.TREE_OF_THOUGHTS),
        (features.needs_decomposition, Technique.LEAST_TO_MOST),
        (features.needs_abstraction, Technique.STEP_BACK),
        (features.needs_reasoning, Technique.ZERO_SHOT_COT),
    ]
    for condition, technique in ordered_preferences:
        if condition and technique in candidates:
            return technique
    return Technique.ZERO_SHOT


def _select_lightweight(features: RequestFeatures) -> Technique:
    if features.has_reasoning_examples:
        return Technique.FEW_SHOT_COT
    if features.has_examples:
        return Technique.FEW_SHOT
    if (
        features.needs_reasoning
        or features.needs_multipath
        or features.needs_decomposition
        or features.needs_abstraction
    ):
        return Technique.ZERO_SHOT_COT
    return Technique.ZERO_SHOT


def _routing_reasons(
    selected: Technique, event: StageEvent, features: RequestFeatures
) -> list[str]:
    reasons = [
        f"Candidate pool was chosen for {event.value}.",
    ]
    if selected is Technique.FEW_SHOT:
        reasons.append("Few-shot won because examples or strict formatting are important.")
    elif selected is Technique.ZERO_SHOT_COT:
        reasons.append("Zero-shot reasoning won because the task asks for analysis without reasoning examples.")
    elif selected is Technique.FEW_SHOT_COT:
        reasons.append("Few-shot reasoning won because reasoning examples were supplied.")
    elif selected is Technique.LEAST_TO_MOST:
        reasons.append("Least-to-most won because ordered decomposition is useful.")
    elif selected is Technique.STEP_BACK:
        reasons.append("Step-back won because abstraction or principles are useful before solving.")
    elif selected is Technique.TREE_OF_THOUGHTS:
        reasons.append("Tree-of-thoughts won because multiple candidate paths should be compared.")
    else:
        reasons.append("Zero-shot won because the task is direct enough for a lightweight prompt.")
    if event in IN_STAGE_EVENTS:
        reasons.append("Stage-internal work uses the lightweight skill pool.")
    return reasons
