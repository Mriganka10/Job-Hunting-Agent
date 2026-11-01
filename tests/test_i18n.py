"""Interface languages (English, Arabic) and the language pack."""
import json
import re
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from job_hunting_agent.pages import localize_document, normalize_lang
from job_hunting_agent.web import app

PACKS = Path(__file__).resolve().parents[1] / "src" / "job_hunting_agent" / "static" / "ui" / "i18n"


def _pack(code: str) -> dict:
    text = (PACKS / f"{code}.js").read_text(encoding="utf-8")
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def _client(email: str, lang: str | None = None) -> TestClient:
    client = TestClient(app)
    if lang:
        client.cookies.set("jha_lang", lang)
    otp = client.post("/api/auth/request-otp", data={"email": email}).json()["dev_otp"]
    client.post("/api/auth/verify", data={"email": email, "otp": otp})
    return client


def test_arabic_pack_is_complete_and_hindi_is_not_published():
    arabic = _pack("ar")
    assert len(arabic["strings"]) > 600
    assert arabic["html"].keys() == {"consent", "required-note"}
    for source, _ in arabic["patterns"]:
        re.compile(source)
    # Every translation is really in Arabic script.
    assert all(re.search(r"[؀-ۿ]", value) for value in arabic["strings"].values())
    assert not (PACKS / "hi.js").exists()


def test_language_pack_matches_the_generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location("i18n_strings", Path(__file__).resolve().parents[1] / "scripts" / "i18n_strings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.parse_rows()
    assert rows.keys() == _pack("ar")["strings"].keys(), "Run python scripts/i18n_strings.py after editing translations."
    assert module.ENABLED_PACKS == ("ar",)


def test_documents_get_language_direction_and_translator():
    html = '<!doctype html><html lang="en" data-theme="dark"><head><title>x</title></head><body></body></html>'
    arabic = localize_document(html, "ar")
    assert '<html lang="ar" dir="rtl" data-theme="dark">' in arabic
    assert "/static/ui/i18n/ar.js" in arabic and "/static/ui/i18n.js" in arabic
    english = localize_document(html, "fr")  # unknown languages fall back to English
    assert '<html lang="en" dir="ltr"' in english and "/static/ui/i18n/" not in english and "/static/ui/i18n.js" in english
    assert normalize_lang("AR") == "ar" and normalize_lang(None) == "en"
    # Hindi is switched off: an old "hi" choice falls back to English.
    assert normalize_lang("hi") == "en"
    hindi = localize_document(html, "hi")
    assert '<html lang="en" dir="ltr"' in hindi and "/static/ui/i18n/hi.js" not in hindi


def test_every_page_follows_the_language_cookie():
    client = _client(f"lang-{uuid4().hex}@example.com", "ar")
    for path in ("/", "/progress", "/privacy", "/mock-test", "/mock-interview"):
        page = client.get(path)
        assert page.status_code == 200
        assert '<html lang="ar" dir="rtl"' in page.text, path
        assert "/static/ui/i18n/ar.js" in page.text and "data-lang-picker" in page.text, path
        assert page.headers["content-language"] == "ar"
        assert 'value="hi"' not in page.text  # the picker offers English and Arabic only
    anonymous = TestClient(app)
    anonymous.cookies.set("jha_lang", "ar")
    for path in ("/login", "/register"):
        page = anonymous.get(path)
        assert '<html lang="ar" dir="rtl"' in page.text and "data-lang-picker" in page.text
    assert TestClient(app).get("/static/ui/i18n/ar.js").status_code == 200
    old_choice = _client(f"lang-hi-{uuid4().hex}@example.com", "hi").get("/")
    assert '<html lang="en" dir="ltr"' in old_choice.text and old_choice.headers["content-language"] == "en"


def test_required_fields_are_marked_and_optional_ones_are_not():
    page = _client(f"marks-{uuid4().hex}@example.com").get("/").text
    for field in ("name", "phone", "target_roles", "locations", "skills", "experience_years", "max_jobs_per_portal", "application_mode"):
        tag = re.search(rf'<(?:input|textarea|select) id="{field}"[^>]*>', page).group(0)
        assert "required" in tag and "data-label=" in tag, field
    for field in ("linkedin_profile_url", "naukri_profile_url", "job_description"):
        tag = re.search(rf'<(?:input|textarea) id="{field}"[^>]*>', page).group(0)
        assert "required" not in tag, field
    assert 'id="missing-dialog"' in page and "Fields marked" in page
