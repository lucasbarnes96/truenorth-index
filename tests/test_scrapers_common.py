from __future__ import annotations

import ssl
import unittest
from unittest.mock import patch

from scrapers.common import FetchError, fetch_url


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self):
        return b"ok"


class ScrapersCommonTests(unittest.TestCase):
    def test_fetch_url_defaults_to_verified_tls(self) -> None:
        with patch("urllib.request.urlopen", return_value=_FakeResponse()) as urlopen:
            text = fetch_url("https://example.com", retries=0)
        self.assertEqual("ok", text)
        self.assertIn("context", urlopen.call_args.kwargs)
        self.assertIsNone(urlopen.call_args.kwargs["context"])

    def test_fetch_url_uses_insecure_context_when_verify_false(self) -> None:
        with patch("urllib.request.urlopen", return_value=_FakeResponse()) as urlopen:
            text = fetch_url(
                "https://crtc.gc.ca/eng/publications/reports/policymonitoring/2024/index.htm",
                retries=0,
                verify=False,
                allowed_insecure_hosts={"crtc.gc.ca"},
            )
        self.assertEqual("ok", text)
        self.assertIn("context", urlopen.call_args.kwargs)
        self.assertIsInstance(urlopen.call_args.kwargs["context"], ssl.SSLContext)

    def test_fetch_url_rejects_insecure_mode_for_disallowed_host(self) -> None:
        with self.assertRaises(FetchError):
            fetch_url(
                "https://example.com",
                retries=0,
                verify=False,
                allowed_insecure_hosts={"crtc.gc.ca"},
            )


if __name__ == "__main__":
    unittest.main()
