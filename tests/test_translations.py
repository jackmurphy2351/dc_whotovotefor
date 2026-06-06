"""Validate the language overlays against the canonical English content.

Hard-fails on structural drift (an overlay referencing an id/field that doesn't
exist in English); only reports — never fails — on missing translations, since
per-field English fallback is intentional.
"""

from pathlib import Path

import pytest
import yaml
from markupsafe import escape

from helpmevote import create_app
from helpmevote.i18n import SUPPORTED_LANGUAGES

_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
_OVERLAY_LANGS = [lang for lang in SUPPORTED_LANGUAGES if lang != "en"]

# Allowed keys per overlay record — guards against typos like `propmt` that would
# otherwise silently never apply.
_ELECTION_KEYS = {"slug", "title", "short_description", "whats_at_stake"}
_ISSUE_KEYS = {"id", "label", "description"}
_QUESTION_KEYS = {"id", "prompt", "explanation"}
_CAND_KEYS = {"id", "short_bio", "long_bio", "positions", "advisories"}
_POSITION_KEYS = {"question_id", "explanation", "quote"}
_ADVISORY_KEYS = {"organization", "text"}


def _load(path: Path):
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text()) or []


@pytest.fixture(scope="module")
def english():
    return create_app("development").config["CONTENT"]


@pytest.fixture(scope="module")
def app():
    return create_app("development")


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_election_overlay_ids_and_keys(english, lang):
    for item in _load(_CONTENT_DIR / lang / "elections.yaml"):
        assert item["slug"] in english.elections, f"{lang}: unknown election {item['slug']}"
        assert set(item) <= _ELECTION_KEYS, f"{lang}: bad keys {set(item) - _ELECTION_KEYS}"


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_issue_overlay_ids_and_keys(english, lang):
    for item in _load(_CONTENT_DIR / lang / "issues.yaml"):
        assert item["id"] in english.issues, f"{lang}: unknown issue {item['id']}"
        assert set(item) <= _ISSUE_KEYS, f"{lang}: bad keys {set(item) - _ISSUE_KEYS}"


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_question_overlay_ids_and_keys(english, lang):
    for item in _load(_CONTENT_DIR / lang / "questions.yaml"):
        assert item["id"] in english.questions, f"{lang}: unknown question {item['id']}"
        assert set(item) <= _QUESTION_KEYS, f"{lang}: bad keys {set(item) - _QUESTION_KEYS}"


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_candidate_overlay_ids_and_keys(english, lang):
    cdir = _CONTENT_DIR / lang / "candidates"
    if not cdir.exists():
        return
    for path in cdir.glob("*.yaml"):
        slug = path.stem
        assert slug in english.elections, f"{lang}: candidates file for unknown race {slug}"
        for item in _load(path):
            cand = english.candidates_by_id.get(item["id"])
            assert cand is not None, f"{lang}: unknown candidate {item['id']}"
            assert cand.election_slug == slug, f"{lang}: {item['id']} not in race {slug}"
            assert set(item) <= _CAND_KEYS, f"{lang}: bad keys {set(item) - _CAND_KEYS}"

            known_qids = {p.question_id for p in cand.positions}
            for pos in item.get("positions", []):
                assert set(pos) <= _POSITION_KEYS, f"{lang}: bad position keys in {item['id']}"
                assert pos["question_id"] in known_qids, (
                    f"{lang}: {item['id']} has no English position for {pos['question_id']}"
                )

            known_orgs = {a.organization for a in cand.advisories}
            for adv in item.get("advisories", []):
                assert set(adv) <= _ADVISORY_KEYS, f"{lang}: bad advisory keys in {item['id']}"
                assert adv["organization"] in known_orgs, (
                    f"{lang}: {item['id']} has no English advisory for {adv['organization']}"
                )


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_translated_content_has_identical_structure(app, english, lang):
    """The merged overlay must have exactly the same id/slug sets as English."""
    translated = app.config["CONTENT_BY_LANG"][lang]
    assert set(translated.elections) == set(english.elections)
    assert set(translated.issues) == set(english.issues)
    assert set(translated.questions) == set(english.questions)
    assert set(translated.candidates_by_id) == set(english.candidates_by_id)


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_ui_keys_are_subset_of_english(app, lang):
    en_keys = set(app.config["UI_BY_LANG"]["en"])
    lang_keys = set(app.config["UI_BY_LANG"][lang])
    orphans = lang_keys - en_keys
    assert not orphans, f"{lang}/ui.yaml has keys not in en/ui.yaml: {orphans}"


@pytest.mark.parametrize("lang", _OVERLAY_LANGS)
def test_overlay_preserves_stances_and_sources(app, english, lang):
    """Translation must never touch a candidate's stance or sources."""
    translated = app.config["CONTENT_BY_LANG"][lang]
    for cid, en_cand in english.candidates_by_id.items():
        tr_cand = translated.candidates_by_id[cid]
        en_pos = {p.question_id: p for p in en_cand.positions}
        for tp in tr_cand.positions:
            ep = en_pos[tp.question_id]
            assert tp.stance == ep.stance
            assert tp.sources == ep.sources


# --- Spanish smoke tests ----------------------------------------------------

@pytest.fixture
def client():
    app = create_app("development")
    app.config["TESTING"] = True
    return app.test_client()


def test_spanish_home_renders(client):
    resp = client.get("/es/")
    assert resp.status_code == 200
    assert b'<html lang="es"' in resp.data
    assert resp.headers["Content-Language"] == "es"
    assert b"Elecciones" in resp.data


def test_spanish_candidate_page_is_translated(client):
    resp = client.get("/es/candidate/ward1/jackie-reyes-yanes")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Name stays English; bio and a position are translated.
    assert "Jackie Reyes Yanes" in body
    assert "madre adolescente" in body  # from the translated long_bio
    assert "Posiciones sobre los temas" in body  # translated section heading


def test_spanish_falls_back_to_english_for_untranslated_candidate(client, english):
    # Pick any candidate with no es overlay entry; their English long_bio should
    # render under /es (per-field fallback) while the chrome stays Spanish.
    es_ids = set()
    for path in (_CONTENT_DIR / "es" / "candidates").glob("*.yaml"):
        for c in _load(path):
            es_ids.add(c["id"])
    target = next(
        (c for c in english.candidates_by_id.values()
         if c.id not in es_ids and c.long_bio.strip()),
        None,
    )
    if target is None:
        pytest.skip("all candidates are translated — no fallback case to test")
    resp = client.get(f"/es/candidate/{target.election_slug}/{target.id}")
    assert resp.status_code == 200
    assert b"Posiciones sobre los temas" in resp.data  # chrome is Spanish
    snippet = str(escape(target.long_bio.strip().splitlines()[0][:50]))
    assert snippet.encode() in resp.data  # English bio shown via fallback


def test_spanish_about_page_is_translated(client):
    resp = client.get("/es/about")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Acerca de este sitio" in body
    assert "Ejemplos prácticos" in body  # worked-examples heading
    assert "0 pasos de diferencia" in body  # plural + .format line


def test_spanish_resource_page_is_translated(client):
    resp = client.get("/es/resources/methodology")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Cómo asignamos las posturas" in body  # translated title (ui.yaml)
    assert "Traducciones e idioma" in body  # translated body section


def test_resource_body_links_get_language_prefix(client):
    # The /resources/ranked_choice link inside primary_vs_general.md is rewritten
    # to the active language so it doesn't 404 under /<lang_code>/ routing.
    resp = client.get("/es/resources/primary_vs_general")
    assert b'href="/es/resources/ranked_choice"' in resp.data
    en = client.get("/en/resources/primary_vs_general")
    assert b'href="/en/resources/ranked_choice"' in en.data
