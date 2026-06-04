import pytest

from helpmevote import create_app


@pytest.fixture
def client():
    app = create_app("development")
    app.config["TESTING"] = True
    return app.test_client()


def test_unknown_url_returns_custom_404(client):
    resp = client.get("/this-page-does-not-exist")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data
    # Custom page extends base.html, so the site footer is present.
    assert b"we don't collect your data" in resp.data


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    csp = resp.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_hsts_absent_in_development(client):
    resp = client.get("/")
    assert "Strict-Transport-Security" not in resp.headers


def test_hsts_present_in_production():
    app = create_app("production")
    app.config["TESTING"] = True
    resp = app.test_client().get("/")
    assert "Strict-Transport-Security" in resp.headers
    assert "max-age=31536000" in resp.headers["Strict-Transport-Security"]
