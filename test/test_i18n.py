import re
import unittest

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from utils.i18n import (
    FALLBACK_LOCALE,
    SUPPORTED_LOCALES,
    MESSAGES,
    get_locale,
    parse_accept_language,
    reset_locale,
    set_locale,
    t,
)


class TestParseAcceptLanguage(unittest.TestCase):
    def test_exact_match(self) -> None:
        self.assertEqual(parse_accept_language("en"), "en")

    def test_region_subtag_is_stripped(self) -> None:
        self.assertEqual(parse_accept_language("vi-VN"), "vi")

    def test_quality_values_are_ordered(self) -> None:
        self.assertEqual(parse_accept_language("fr;q=0.9,en;q=0.8,vi;q=1.0"), "vi")

    def test_unsupported_falls_back(self) -> None:
        self.assertEqual(parse_accept_language("fr-FR"), FALLBACK_LOCALE)

    def test_missing_header_falls_back(self) -> None:
        self.assertEqual(parse_accept_language(None), FALLBACK_LOCALE)
        self.assertEqual(parse_accept_language(""), FALLBACK_LOCALE)

    def test_malformed_quality_is_ignored(self) -> None:
        self.assertEqual(parse_accept_language("en;q=oops"), "en")


class TestCatalog(unittest.TestCase):
    def test_all_locales_share_the_same_keys(self) -> None:
        reference = set(MESSAGES[FALLBACK_LOCALE])
        for locale in SUPPORTED_LOCALES:
            self.assertEqual(set(MESSAGES[locale]), reference, f"locale {locale} key mismatch")

    def test_unknown_key_returns_the_key(self) -> None:
        self.assertEqual(t("en", "no.such.key"), "no.such.key")

    def test_unknown_locale_uses_fallback(self) -> None:
        key = next(iter(MESSAGES[FALLBACK_LOCALE]))
        self.assertEqual(t("fr", key), MESSAGES[FALLBACK_LOCALE][key])


class TestCatalogCompleteness(unittest.TestCase):
    def test_no_chinese_in_en_or_vi(self) -> None:
        cjk = re.compile(r"[一-鿿]")
        for locale in ("en", "vi"):
            for key, value in MESSAGES[locale].items():
                self.assertIsNone(cjk.search(value), f"{locale}.{key} still holds Chinese: {value}")


class TestLocaleContextVar(unittest.TestCase):
    def test_get_locale_defaults_to_fallback_when_nothing_set_it(self) -> None:
        self.assertEqual(get_locale(), FALLBACK_LOCALE)

    def test_set_locale_is_visible_to_get_locale_and_t(self) -> None:
        token = set_locale("vi")
        try:
            self.assertEqual(get_locale(), "vi")
            self.assertEqual(t("auth.key_invalid"), MESSAGES["vi"]["auth.key_invalid"])
        finally:
            reset_locale(token)
        self.assertEqual(get_locale(), FALLBACK_LOCALE)


def _locale_probe_app() -> FastAPI:
    """A minimal app wired the same way as api/app.py's locale middleware, kept
    separate from the real app so these tests do not boot its background
    watchers, storage and other unrelated services."""
    from api.support import LocaleMiddleware

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)

    @app.get("/async-echo")
    async def async_echo():
        return {"message": t("auth.key_invalid")}

    @app.get("/sync-echo")
    def sync_echo():
        return {"message": t("auth.key_invalid")}

    @app.get("/threadpool-echo")
    async def threadpool_echo():
        def work() -> str:
            return t("auth.key_invalid")

        return {"message": await run_in_threadpool(work)}

    @app.get("/stream-echo")
    async def stream_echo():
        async def body():
            for _ in range(3):
                yield f"{t('auth.key_invalid')}\n"

        return StreamingResponse(body(), media_type="text/event-stream")

    return app


class TestLocaleMiddleware(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(_locale_probe_app())

    def test_middleware_value_is_visible_to_t_in_an_async_endpoint(self) -> None:
        response = self.client.get("/async-echo", headers={"Accept-Language": "vi"})
        self.assertEqual(response.json()["message"], MESSAGES["vi"]["auth.key_invalid"])

    def test_middleware_value_is_visible_to_t_in_a_sync_endpoint(self) -> None:
        # Starlette runs a plain `def` endpoint in a worker thread; this confirms
        # the ContextVar set on the request's asyncio task still reaches it there.
        response = self.client.get("/sync-echo", headers={"Accept-Language": "en"})
        self.assertEqual(response.json()["message"], MESSAGES["en"]["auth.key_invalid"])

    def test_middleware_value_is_visible_through_explicit_threadpool_offload(self) -> None:
        # Mirrors services/content_filter.check_request, invoked via
        # `await run_in_threadpool(check_request, text)` from async handlers.
        response = self.client.get("/threadpool-echo", headers={"Accept-Language": "vi"})
        self.assertEqual(response.json()["message"], MESSAGES["vi"]["auth.key_invalid"])

    def test_middleware_value_is_visible_throughout_a_streamed_response(self) -> None:
        response = self.client.get("/stream-echo", headers={"Accept-Language": "vi"})
        expected = MESSAGES["vi"]["auth.key_invalid"]
        self.assertEqual(response.text, f"{expected}\n" * 3)

    def test_locale_does_not_leak_between_requests(self) -> None:
        first = self.client.get("/async-echo", headers={"Accept-Language": "vi"})
        second = self.client.get("/async-echo")
        third = self.client.get("/async-echo", headers={"Accept-Language": "en"})
        fourth = self.client.get("/async-echo")

        self.assertEqual(first.json()["message"], MESSAGES["vi"]["auth.key_invalid"])
        self.assertEqual(second.json()["message"], MESSAGES[FALLBACK_LOCALE]["auth.key_invalid"])
        self.assertEqual(third.json()["message"], MESSAGES["en"]["auth.key_invalid"])
        self.assertEqual(fourth.json()["message"], MESSAGES[FALLBACK_LOCALE]["auth.key_invalid"])


class _MemoryAccountStorage:
    """Minimal StorageBackend stub, mirrors test_relogin_unknown_token.py's fixture."""

    def __init__(self, accounts: list[dict] | None = None) -> None:
        self.accounts = list(accounts or [])

    def load_accounts(self) -> list[dict]:
        return list(self.accounts)

    def save_accounts(self, accounts: list[dict]) -> None:
        self.accounts = list(accounts)

    def load_auth_keys(self) -> list[dict]:
        return []

    def save_auth_keys(self, auth_keys: list[dict]) -> None:
        pass

    def health_check(self) -> dict:
        return {"ok": True}

    def get_backend_info(self) -> dict:
        return {"type": "memory"}


class TestReloginWorkerStoresKeysNotSentences(unittest.TestCase):
    """re_login_accounts runs on a thread with no request in scope; it must
    store a translation key plus a marker, never a sentence baked into the
    writer's own locale."""

    def test_unknown_token_stores_a_key(self) -> None:
        from services.account_service import AccountService

        service = AccountService(_MemoryAccountStorage())
        service.re_login_accounts(["token-not-in-pool"], progress_id="p-unknown")

        entry = service.get_relogin_progress("p-unknown")["results"][0]
        self.assertEqual(entry["error"], "account.not_found")
        self.assertTrue(entry["error_is_key"])
        cjk = re.compile(r"[一-鿿]")
        self.assertIsNone(cjk.search(entry["error"]))

    def test_account_missing_credentials_stores_a_key(self) -> None:
        from services.account_service import AccountService

        service = AccountService(_MemoryAccountStorage([{"access_token": "tok-no-pass"}]))
        service.re_login_accounts(["tok-no-pass"], progress_id="p-nocreds")

        entry = service.get_relogin_progress("p-nocreds")["results"][0]
        self.assertEqual(entry["error"], "account.no_email_password")
        self.assertTrue(entry["error_is_key"])


class TestReloginProgressRendersPerReaderLocale(unittest.TestCase):
    """The polling endpoint renders a stored key against its own request's
    locale, not the locale of whoever wrote the record."""

    def setUp(self) -> None:
        from api.accounts import _render_relogin_results

        self.render = _render_relogin_results

    def test_renders_vi(self) -> None:
        results = [{"token": "tok-1", "status": "跳过", "error": "account.not_found", "error_is_key": True}]
        token = set_locale("vi")
        try:
            rendered = self.render(results)
        finally:
            reset_locale(token)
        self.assertEqual(rendered[0]["error"], MESSAGES["vi"]["account.not_found"])

    def test_renders_en(self) -> None:
        results = [{"token": "tok-1", "status": "跳过", "error": "account.not_found", "error_is_key": True}]
        token = set_locale("en")
        try:
            rendered = self.render(results)
        finally:
            reset_locale(token)
        self.assertEqual(rendered[0]["error"], MESSAGES["en"]["account.not_found"])

    def test_renders_zh_with_no_locale_set(self) -> None:
        results = [{"token": "tok-1", "status": "跳过", "error": "account.not_found", "error_is_key": True}]
        rendered = self.render(results)
        self.assertEqual(rendered[0]["error"], "账号不存在")

    def test_passthrough_error_survives_unchanged(self) -> None:
        # Upstream failure codes (e.g. from a password re-login attempt) have no
        # catalog key and must reach the reader exactly as the writer saw them.
        results = [{"token": "tok-2", "status": "异常", "error": "invalid_password", "error_is_key": False}]
        token = set_locale("vi")
        try:
            rendered = self.render(results)
        finally:
            reset_locale(token)
        self.assertEqual(rendered[0]["error"], "invalid_password")

    def test_internal_marker_does_not_leak_onto_the_wire(self) -> None:
        results = [{"token": "tok-1", "status": "跳过", "error": "account.not_found", "error_is_key": True}]
        rendered = self.render(results)
        self.assertNotIn("error_is_key", rendered[0])


def _relogin_progress_probe_app() -> FastAPI:
    """Exercises the exact function the real GET /re-login/progress endpoint
    uses to render stored results, through the same LocaleMiddleware, without
    booting the full app (auth, storage, background watchers)."""
    from api.support import LocaleMiddleware
    from api.accounts import _render_relogin_results

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)

    @app.get("/relogin-progress")
    async def relogin_progress():
        results = [{"token": "tok-1", "status": "跳过", "error": "account.not_found", "error_is_key": True}]
        return {"results": _render_relogin_results(results)}

    return app


class TestReloginProgressEndpointRendersPerRequestLocale(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(_relogin_progress_probe_app())

    def test_vi_header(self) -> None:
        response = self.client.get("/relogin-progress", headers={"Accept-Language": "vi"})
        self.assertEqual(response.json()["results"][0]["error"], MESSAGES["vi"]["account.not_found"])

    def test_en_header(self) -> None:
        response = self.client.get("/relogin-progress", headers={"Accept-Language": "en"})
        self.assertEqual(response.json()["results"][0]["error"], MESSAGES["en"]["account.not_found"])

    def test_no_header_falls_back_to_zh(self) -> None:
        response = self.client.get("/relogin-progress")
        self.assertEqual(response.json()["results"][0]["error"], "账号不存在")


if __name__ == "__main__":
    unittest.main()
