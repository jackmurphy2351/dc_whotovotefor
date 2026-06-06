from pathlib import Path

import pytest
import yaml

from helpmevote import create_app
from helpmevote.data_loader import load_all_content


def write_yaml(path: Path, data) -> None:
    path.write_text(yaml.dump(data, allow_unicode=True))


def build_content_dir(tmp_path: Path) -> Path:
    """Two races (mayor, ward1) sharing the TOPA question, so answer carry-over
    and the all-races flow can be exercised."""
    (tmp_path / "candidates").mkdir()

    write_yaml(tmp_path / "elections.yaml", [
        {
            "slug": "mayor",
            "title": "Mayor",
            "short_description": "Choose the mayor.",
            "whats_at_stake": "Stakes.",
            "election_date": "2026-06-02",
            "sources": [],
        },
        {
            "slug": "ward1",
            "title": "Ward 1",
            "short_description": "Choose the Ward 1 councilmember.",
            "whats_at_stake": "Stakes.",
            "election_date": "2026-06-02",
            "sources": [],
        },
    ])

    write_yaml(tmp_path / "issues.yaml", [
        {"id": "housing", "label": "Housing", "description": "Housing issues."},
        {"id": "transit", "label": "Transit", "description": "Transit issues."},
    ])

    write_yaml(tmp_path / "questions.yaml", [
        {"id": "q_topa", "issue": "housing", "prompt": "Support TOPA?",
         "applies_to_elections": ["mayor", "ward1"], "explanation": "", "sources": []},
        {"id": "q_social", "issue": "housing", "prompt": "Build social housing?",
         "applies_to_elections": ["mayor"], "explanation": "", "sources": []},
        {"id": "q_bikes", "issue": "transit", "prompt": "Add bike lanes?",
         "applies_to_elections": ["mayor"], "explanation": "", "sources": []},
    ])

    def position(qid, stance, who="alice"):
        return {
            "question_id": qid,
            "stance": stance,
            "explanation": f"Position on {qid}.",
            "sources": [{
                "url": f"https://{who}.com", "title": f"{who} platform",
                "publisher": f"{who}.com", "accessed": "2026-05-27",
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

    write_yaml(tmp_path / "candidates" / "ward1.yaml", [
        {
            "id": "bob", "name": "Bob", "election_slug": "ward1",
            "in_fair_elections": False, "endorsements": [],
            "short_bio": "A candidate.", "long_bio": "A longer bio.",
            "campaign_url": None, "advisories": [], "sources": [],
            "positions": [
                position("q_topa", 2, who="bob"),
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
    resp = client.post("/en/quiz/mayor/start", data={"selected": ["q_topa", "q_social"]})
    assert resp.status_code == 302
    assert "/en/quiz/mayor" in resp.headers["Location"]

    with client.session_transaction() as sess:
        assert sess["quiz_selected_mayor"] == ["q_topa", "q_social"]


def test_quiz_total_reflects_subset(client):
    client.post("/en/quiz/mayor/start", data={"selected": ["q_topa", "q_social"]})
    page = client.get("/en/quiz/mayor").get_data(as_text=True)
    assert "Question 1 of 2" in page


def test_results_score_only_selected_questions(client):
    # Seed a selection of 2 questions but a stale answer for the deselected one.
    with client.session_transaction() as sess:
        sess["quiz_selected_mayor"] = ["q_topa", "q_social"]
        sess["quiz_answers"] = {"q_topa": 1, "q_social": 1, "q_bikes": 1}

    page = client.get("/en/results/mayor").get_data(as_text=True)
    # Agree (1) vs strongly supports (2) on both selected questions → 75%.
    # If the deselected bikes question (cand -2) counted, it would drag this lower.
    assert "75%" in page
    assert "bike lanes" not in page.lower()


def test_empty_selection_rerenders_with_error(client):
    resp = client.post("/en/quiz/mayor/start", data={})
    assert resp.status_code == 200
    assert "at least one question" in resp.get_data(as_text=True).lower()

    with client.session_transaction() as sess:
        assert "quiz_selected_mayor" not in sess


def test_backward_compat_no_selection_serves_all(client):
    page = client.get("/en/quiz/mayor").get_data(as_text=True)
    assert "Question 1 of 3" in page


def test_answers_carry_over_between_races(client):
    # One shared answer store feeds every race's results.
    with client.session_transaction() as sess:
        sess["quiz_answers"] = {"q_topa": 2, "q_social": 2, "q_bikes": -2}

    mayor = client.get("/en/results/mayor").get_data(as_text=True)
    assert "Alice" in mayor and "100%" in mayor  # perfect match on all 3

    ward1 = client.get("/en/results/ward1").get_data(as_text=True)
    # Bob is scored from the same store, on the one shared question (q_topa).
    assert "Bob" in ward1 and "100%" in ward1


def test_results_all_renders_every_race(client):
    with client.session_transaction() as sess:
        sess["quiz_answers"] = {"q_topa": 2, "q_social": 2, "q_bikes": -2}

    page = client.get("/en/results/all").get_data(as_text=True)
    assert "Mayor" in page
    assert "Ward 1" in page
    assert "Alice" in page
    assert "Bob" in page


def test_per_race_results_link_back_to_all_races(client):
    with client.session_transaction() as sess:
        sess["quiz_answers"] = {"q_topa": 2, "q_social": 2, "q_bikes": -2}

    page = client.get("/en/results/mayor").get_data(as_text=True)
    assert "/en/results/all" in page


def test_results_all_empty_prompts_to_quiz(client):
    page = client.get("/en/results/all").get_data(as_text=True)
    assert "No answers recorded" in page


def test_all_quiz_steps_over_union_and_writes_global_answers(client):
    # No selection stored → the union of all questions (3 distinct) is served.
    page = client.get("/en/quiz/all").get_data(as_text=True)
    assert "Question 1 of 3" in page

    client.post("/en/quiz/all", data={"step": 0, "stance": 2})
    with client.session_transaction() as sess:
        assert sess["quiz_answers"]["q_topa"] == 2


def test_all_start_shows_question_counts(client):
    page = client.get("/en/quiz/all/start").get_data(as_text=True)
    assert "Housing (2 questions)" in page
    assert "Transit (1 question)" in page


def test_reset_clears_shared_answers_and_selections(client):
    with client.session_transaction() as sess:
        sess["quiz_answers"] = {"q_topa": 2}
        sess["quiz_selected_mayor"] = ["q_topa"]

    client.get("/en/quiz/mayor/reset")
    with client.session_transaction() as sess:
        assert "quiz_answers" not in sess
        assert "quiz_selected_mayor" not in sess
