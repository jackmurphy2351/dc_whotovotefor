from pathlib import Path

import pytest
import yaml

from helpmevote import create_app
from helpmevote.data_loader import load_all_content


def write_yaml(path: Path, data) -> None:
    path.write_text(yaml.dump(data, allow_unicode=True))


def build_content_dir(tmp_path: Path) -> Path:
    """Content with two issues and three mayoral questions for one candidate."""
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
        {"id": "housing", "label": "Housing", "description": "Housing issues."},
        {"id": "transit", "label": "Transit", "description": "Transit issues."},
    ])

    write_yaml(tmp_path / "questions.yaml", [
        {"id": "q_topa", "issue": "housing", "prompt": "Support TOPA?",
         "applies_to_elections": ["mayor"], "explanation": "", "sources": []},
        {"id": "q_social", "issue": "housing", "prompt": "Build social housing?",
         "applies_to_elections": ["mayor"], "explanation": "", "sources": []},
        {"id": "q_bikes", "issue": "transit", "prompt": "Add bike lanes?",
         "applies_to_elections": ["mayor"], "explanation": "", "sources": []},
    ])

    def position(qid, stance):
        return {
            "question_id": qid,
            "stance": stance,
            "explanation": f"Position on {qid}.",
            "sources": [{
                "url": "https://alice.com", "title": "Alice platform",
                "publisher": "alice.com", "accessed": "2026-05-27",
            }],
        }

    write_yaml(tmp_path / "candidates" / "mayor.yaml", [
        {
            "id": "alice", "name": "Alice", "election_slug": "mayor",
            "in_fair_elections": True, "endorsements": [],
            "short_bio": "A candidate.", "long_bio": "A longer bio.",
            "campaign_url": None, "advisories": [], "sources": [],
            "positions": [
                position("q_topa", 2),
                position("q_social", 2),
                position("q_bikes", -2),
            ],
        }
    ])

    return tmp_path


@pytest.fixture
def client(tmp_path):
    app = create_app("default")
    app.config["CONTENT"] = load_all_content(build_content_dir(tmp_path))
    app.config["TESTING"] = True
    return app.test_client()


def test_posting_subset_stores_selection_and_redirects(client):
    resp = client.post("/quiz/mayor/start", data={"selected": ["q_topa", "q_social"]})
    assert resp.status_code == 302
    assert "/quiz/mayor" in resp.headers["Location"]

    with client.session_transaction() as sess:
        assert sess["quiz_selected_mayor"] == ["q_topa", "q_social"]


def test_quiz_total_reflects_subset(client):
    client.post("/quiz/mayor/start", data={"selected": ["q_topa", "q_social"]})
    page = client.get("/quiz/mayor").get_data(as_text=True)
    assert "Question 1 of 2" in page


def test_results_score_only_selected_questions(client):
    # Seed a selection of 2 questions but a stale answer for the deselected one.
    with client.session_transaction() as sess:
        sess["quiz_selected_mayor"] = ["q_topa", "q_social"]
        sess["quiz_answers_mayor"] = {"q_topa": 1, "q_social": 1, "q_bikes": 1}

    page = client.get("/results/mayor").get_data(as_text=True)
    # Agree (1) vs strongly supports (2) on both selected questions → 75%.
    # If the deselected bikes question (cand -2) counted, it would drag this lower.
    assert "75%" in page
    assert "bike lanes" not in page.lower()


def test_empty_selection_rerenders_with_error(client):
    resp = client.post("/quiz/mayor/start", data={})
    assert resp.status_code == 200
    assert "at least one question" in resp.get_data(as_text=True).lower()

    with client.session_transaction() as sess:
        assert "quiz_selected_mayor" not in sess


def test_backward_compat_no_selection_serves_all(client):
    page = client.get("/quiz/mayor").get_data(as_text=True)
    assert "Question 1 of 3" in page
