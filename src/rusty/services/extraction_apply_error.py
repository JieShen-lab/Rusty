from __future__ import annotations


class CandidateApplyError(Exception):
    """An extraction batch failure that can be attributed to one candidate."""

    def __init__(self, candidate_id: str, message: str) -> None:
        self.candidate_id = candidate_id
        super().__init__(message)
