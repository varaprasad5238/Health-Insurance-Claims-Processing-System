from enum import StrEnum


class WorkflowName(StrEnum):
    CODE_INGESTION = "Code Ingestion"
    CURRENT_SPEC_GENERATION = "Current Spec Generation"
    CURRENT_SPEC_REFINEMENT = "Current Spec Refinement"
    CURRENT_SPEC_GENERATION_MAINFRAME = "Current Spec Generation Mainframe"
    TARGET_SPEC_GENERATION = "Target Spec Generation"
    TARGET_SPEC_REFINEMENT = "Target Spec Refinement"
    EPIC_GENERATION = "Epic Generation"
    CHAT = "Chat"
    UNKNOWN = "unknown"
