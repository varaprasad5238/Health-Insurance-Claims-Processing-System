from abc import ABC, abstractmethod
from typing import List, Dict, Any

class DocumentIntelligenceProvider(ABC):
    @abstractmethod
    async def process_document(self, file_id: str, mime_type: str, raw_bytes: bytes) -> Dict[str, Any]:
        """
        Processes a single document and returns a dictionary with:
        - detected_type
        - confidence
        - raw_transcript
        - readability_score
        - quality_flags
        """
        pass

    @abstractmethod
    async def extract_entities(self, transcript: str) -> Dict[str, Any]:
        """
        Extracts structured entities from the text transcript.
        """
        pass

    @abstractmethod
    async def synthesize_decision(self, claim_data: Dict[str, Any], rule_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Synthesizes the member-facing message from rules.
        """
        pass
