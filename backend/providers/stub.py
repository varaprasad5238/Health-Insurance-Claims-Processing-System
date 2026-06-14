from typing import Dict, Any, List
from .base import DocumentIntelligenceProvider

class StubProvider(DocumentIntelligenceProvider):
    async def process_document(self, file_id: str, mime_type: str, raw_bytes: bytes) -> Dict[str, Any]:
        return {
            "detected_type": "PRESCRIPTION",
            "confidence": 0.95,
            "raw_transcript": "Patient: Rajesh Kumar\nRx: Paracetamol",
            "readability_score": 0.90,
            "quality_flags": []
        }

    async def extract_entities(self, transcript: str) -> Dict[str, Any]:
        return {
            "patient_name": "Rajesh Kumar",
            "doctor_name": "Dr. Smith",
            "diagnosis_primary": "Fever",
            "line_items": []
        }

    async def synthesize_decision(self, claim_data: Dict[str, Any], rule_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "member_message": "Your claim has been processed.",
            "ops_summary": "Processed via StubProvider."
        }
