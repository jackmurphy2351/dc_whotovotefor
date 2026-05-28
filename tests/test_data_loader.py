from datetime import date
from pathlib import Path
import textwrap

import pytest
import yaml

from helpmevote.data_loader import load_all_content, validate_content
from helpmevote.models import AppContent, Candidate, Election, Issue, Position, Question, Source


def write_yaml(path: Path, data) -> None:
    path.write_text(yaml.dump(data, allow_unicode=True))


def minimal_content_dir(tmp_path: Path) -> Path:
    """Write a minimal valid content directory."""
    (tmp_path / "candidates").mkdir()

    write_yaml(tmp_path / "elections.yaml", [
        {
            "slug": "mayor",
            "title": "Mayor",
            "short_description": "Choose the mayor.",
            "whats_at_stake": "Stakes.",
            "election_date": "2026-06-02",
            "sources": [],
        }
    ])

    write_yaml(tmp_path / "issues.yaml", [
        {"id": "housing", "label": "Housing", "description": "Housing issues."}
    ])

    write_yaml(tmp_path / "questions.yaml", [
        {
            "id": "q_topa",
            "issue": "housing",
            "prompt": "Support TOPA?",
            "applies_to_elections": ["mayor"],
            "explanation": "",
            "sources": [],
        }
    ])

    write_yaml(tmp_path / "candidates" / "mayor.yaml", [
        {
            "id": "alice",
            "name": "Alice",
            "election_slug": "mayor",
            "in_fair_elections": True,
            "endorsements": [],
            "short_bio": "A candidate.",
            "long_bio": "A longer bio.",
            "campaign_url": None,
            "advisories": [],
            "sources": [],
            "positions": [
                {
                    "question_id": "q_topa",
                    "stance": 2,
                    "explanation": "Supports TOPA.",
                    "sources": [
                        {
                            "url": "https://alice.com",
                            "title": "Alice platform",
                            "publisher": "alice.com",
                            "accessed": "2026-05-27",
                        }
                    ],
                }
            ],
        }
    ])

    return tmp_path


class TestLoadAllContent:
    def test_loads_valid_content(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        content = load_all_content(content_dir)

        assert "mayor" in content.elections
        assert "housing" in content.issues
        assert "q_topa" in content.questions
        assert len(content.candidates["mayor"]) == 1
        assert content.candidates["mayor"][0].name == "Alice"

    def test_questions_by_election_populated(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        content = load_all_content(content_dir)

        assert "q_topa" in [q.id for q in content.questions_by_election["mayor"]]

    def test_candidates_by_id_populated(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        content = load_all_content(content_dir)

        assert "alice" in content.candidates_by_id


class TestValidation:
    def test_missing_source_on_nonzero_stance_raises(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        # Overwrite candidate with a non-zero stance but no sources
        write_yaml(tmp_path / "candidates" / "mayor.yaml", [
            {
                "id": "bob",
                "name": "Bob",
                "election_slug": "mayor",
                "in_fair_elections": False,
                "endorsements": [],
                "short_bio": "",
                "long_bio": "",
                "campaign_url": None,
                "advisories": [],
                "sources": [],
                "positions": [
                    {
                        "question_id": "q_topa",
                        "stance": 1,
                        "explanation": "Supports it.",
                        "sources": [],   # ← missing sources
                    }
                ],
            }
        ])

        with pytest.raises(ValueError, match="no sources"):
            load_all_content(content_dir)

    def test_duplicate_candidate_id_raises(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        original = yaml.safe_load((tmp_path / "candidates" / "mayor.yaml").read_text())
        duplicate = original + [dict(original[0])]  # same id
        write_yaml(tmp_path / "candidates" / "mayor.yaml", duplicate)

        with pytest.raises(ValueError, match="Duplicate candidate id"):
            load_all_content(content_dir)

    def test_unknown_question_id_raises(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        write_yaml(tmp_path / "candidates" / "mayor.yaml", [
            {
                "id": "carol",
                "name": "Carol",
                "election_slug": "mayor",
                "in_fair_elections": False,
                "endorsements": [],
                "short_bio": "",
                "long_bio": "",
                "campaign_url": None,
                "advisories": [],
                "sources": [],
                "positions": [
                    {
                        "question_id": "nonexistent_question",
                        "stance": 1,
                        "explanation": "",
                        "sources": [
                            {
                                "url": "https://example.com",
                                "title": "T",
                                "publisher": "p",
                                "accessed": "2026-05-27",
                            }
                        ],
                    }
                ],
            }
        ])

        with pytest.raises(ValueError, match="unknown question"):
            load_all_content(content_dir)

    def test_unknown_issue_in_question_raises(self, tmp_path):
        content_dir = minimal_content_dir(tmp_path)
        # Remove alice's positions so candidate validation passes first,
        # letting the question→issue check run.
        write_yaml(tmp_path / "candidates" / "mayor.yaml", [
            {
                "id": "alice",
                "name": "Alice",
                "election_slug": "mayor",
                "in_fair_elections": True,
                "endorsements": [],
                "short_bio": "",
                "long_bio": "",
                "campaign_url": None,
                "advisories": [],
                "sources": [],
                "positions": [],
            }
        ])
        write_yaml(tmp_path / "questions.yaml", [
            {
                "id": "q_bad",
                "issue": "nonexistent_issue",
                "prompt": "?",
                "applies_to_elections": ["mayor"],
                "explanation": "",
                "sources": [],
            }
        ])

        with pytest.raises(ValueError, match="unknown issue"):
            load_all_content(content_dir)

    def test_zero_stance_needs_no_source(self, tmp_path):
        """stance=0 (neutral) should not require a source."""
        content_dir = minimal_content_dir(tmp_path)
        write_yaml(tmp_path / "candidates" / "mayor.yaml", [
            {
                "id": "dave",
                "name": "Dave",
                "election_slug": "mayor",
                "in_fair_elections": False,
                "endorsements": [],
                "short_bio": "",
                "long_bio": "",
                "campaign_url": None,
                "advisories": [],
                "sources": [],
                "positions": [
                    {
                        "question_id": "q_topa",
                        "stance": 0,
                        "explanation": "Neutral.",
                        "sources": [],
                    }
                ],
            }
        ])

        content = load_all_content(content_dir)
        assert content.candidates["mayor"][0].id == "dave"
