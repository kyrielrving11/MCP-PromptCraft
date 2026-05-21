"""Stage-aware prompt generation and context compression."""

from .classifier import classify_stage_event
from .compressor import build_compact_context_response, compress_stage_memory
from .config import PromptCraftConfig, load_config
from .context_selector import select_context_packet
from .instruction_builder import (
    HOST_GENERATION_GUIDANCE,
    build_instruction_bundle,
    build_memory_summary,
    list_skill_guides,
    render_instruction_prompt,
)
from .memory_classifier import MemoryClassification, classify_memory_importance
from .models import (
    ContextPacket,
    MemoryImportance,
    PromptRequest,
    RouteResult,
    StageEvent,
    StageMemory,
    TaskMemory,
    Technique,
    WorkingContext,
    memory_importance_or_none,
    technique_or_none,
)
from .router import candidate_pool_for, route_technique, select_technique
from .service import GenerateOptions, process_generate
from .stage_manager import apply_stage_transition
from .state_store import JsonStateStore, TaskState

__all__ = [
    "GenerateOptions",
    "ContextPacket",
    "JsonStateStore",
    "MemoryClassification",
    "MemoryImportance",
    "PromptCraftConfig",
    "PromptRequest",
    "RouteResult",
    "StageEvent",
    "StageMemory",
    "TaskMemory",
    "TaskState",
    "Technique",
    "WorkingContext",
    "apply_stage_transition",
    "candidate_pool_for",
    "classify_stage_event",
    "classify_memory_importance",
    "compress_stage_memory",
    "build_compact_context_response",
    "HOST_GENERATION_GUIDANCE",
    "build_instruction_bundle",
    "build_memory_summary",
    "list_skill_guides",
    "load_config",
    "process_generate",
    "render_instruction_prompt",
    "route_technique",
    "select_technique",
    "select_context_packet",
    "memory_importance_or_none",
    "technique_or_none",
]
