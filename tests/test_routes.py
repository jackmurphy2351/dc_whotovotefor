from pathlib import Path

import pytest
import yaml
from markupsafe import escape

from helpmevote import create_app
from helpmevote.routes.resources import TOPIC_ORDER

# Topics the site actually publishes: in the allowlist *and* backed by a .md file.
# (The index/sitemap skip allowlist entries with no file via `path.exists()`.)
_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
_RESOURCES_DIR = _CONTENT_DIR / "resources"
_PUBLISHED_TOPICS = [t for t in TOPIC_ORDER if (_RESOURCES_DIR / f"{t}.md").exists()]

# Resource titles now live in the English ui.yaml (resources.title.<topic>).
_UI_EN = yaml.safe_load((_CONTENT_DIR / "en" / "ui.yaml").read_text())


def _topic_title(topic: str) -> str:
    return _UI_EN[f"resources.title.{topic}"]


@pytest.fixture
def client():
    app = create_app("development")
    app.config["TESTING"] = True
    return app.test_client()


def _sample_candidate(client):
    """A real (election_slug, candidate) pair from the loaded content."""
    content = client.application.config["CONTENT"]
    for slug, candidates in content.candidates.items():
        if candidates:
            return slug, candidates[0]
    raise AssertionError("no candidates loaded")


def test_unknown_url_returns_custom_404(client):
    resp = client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data
    # Custom page extends base.html, so the site footer is present.
    assert b"collect your data" in resp.data


def test_security_headers_present(client):
    resp = client.get("/en/")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_hsts_absent_in_development(client):
    resp = client.get("/en/")
    assert "Strict-Transport-Security" not in resp.headers


def test_hsts_present_in_production():
    app = create_app("production")
    app.config["TESTING"] = True
    resp = app.test_client().get("/en/")
    assert "Strict-Transport-Security" in resp.headers
    assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]


# --- Content route happy paths ---------------------------------------------

def test_index_lists_every_election(client):
    content = client.application.config["CONTENT"]
    resp = client.get("/en/")
    assert resp.status_code == 200
    for slug, elec in content.elections.items():
        assert f"/en/election/{slug}".encode() in resp.data
        assert elec.title.encode() in resp.data


def test_bare_root_redirects_to_a_language(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].rstrip("/").endswith(("/en", "/es"))


def test_unsupported_language_404(client):
    assert client.get("/fr/").status_code == 404


def test_about_renders(client):
    resp = client.get("/en/about")
    assert resp.status_code == 200


def test_election_page_lists_its_candidates(client):
    slug, cand = _sample_candidate(client)
    resp = client.get(f"/en/election/{slug}")
    assert resp.status_code == 200
    assert cand.name.encode() in resp.data


def test_candidate_page_renders(client):
    slug, cand = _sample_candidate(client)
    resp = client.get(f"/en/candidate/{slug}/{cand.id}")
    assert resp.status_code == 200
    assert cand.name.encode() in resp.data


def test_resources_index_lists_topics(client):
    resp = client.get("/en/resources")
    assert resp.status_code == 200
    # At least one real topic title is listed.
    assert _topic_title("methodology").encode() in resp.data


def test_robots_txt(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/plain")
    assert b"Sitemap:" in resp.data


def test_sitemap_xml(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/xml")
    assert b"<urlset" in resp.data


# --- Error / guard branches -------------------------------------------------

def test_unknown_election_404(client):
    assert client.get("/en/election/does-not-exist").status_code == 404


def test_unknown_candidate_404(client):
    slug, _ = _sample_candidate(client)
    assert client.get(f"/en/candidate/{slug}/no-such-candidate").status_code == 404


def test_candidate_wrong_election_404(client):
    """A valid candidate id under the wrong election slug must 404
    (elections.py guard: cand.election_slug != election_slug)."""
    content = client.application.config["CONTENT"]
    slug, cand = _sample_candidate(client)
    other_slug = next(s for s in content.elections if s != slug)
    assert client.get(f"/en/candidate/{other_slug}/{cand.id}").status_code == 404


def test_unknown_resource_topic_404(client):
    assert client.get("/en/resources/not-a-real-topic").status_code == 404


def test_unknown_quiz_election_404(client):
    assert client.get("/en/quiz/does-not-exist").status_code == 404


def test_unknown_results_election_404(client):
    assert client.get("/en/results/does-not-exist").status_code == 404


# --- Markdown rendering + topic-allowlist sync -----------------------------

@pytest.mark.parametrize("topic", _PUBLISHED_TOPICS)
def test_each_published_topic_renders_with_title(client, topic):
    """Every published topic renders its title (titles may contain escaped HTML
    entities, e.g. '&' -> '&amp;')."""
    resp = client.get(f"/en/resources/{topic}")
    assert resp.status_code == 200, f"{topic} did not render (missing .md file?)"
    assert str(escape(_topic_title(topic))).encode() in resp.data


def test_index_lists_exactly_published_topics(client):
    """The /resources index and the on-disk .md files stay in sync."""
    resp = client.get("/en/resources")
    for topic in _PUBLISHED_TOPICS:
        assert f"/en/resources/{topic}".encode() in resp.data
    # Allowlisted-but-fileless topics must NOT appear as links on the index.
    for topic in set(TOPIC_ORDER) - set(_PUBLISHED_TOPICS):
        assert f"/en/resources/{topic}".encode() not in resp.data


def test_markdown_is_converted_to_html(client):
    """Prove md.markdown() ran: a prose page yields HTML, not raw Markdown."""
    resp = client.get("/en/resources/methodology")
    assert resp.status_code == 200
    body = resp.data
    # A heading became an <h...> tag rather than a literal '# ' line.
    assert b"<h2" in body or b"<h1" in body
    assert b"\n# " not in body
