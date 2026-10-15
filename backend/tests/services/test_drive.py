from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app.services.drive import get_auth_url, SCOPES


class FakeSecrets:
    google_client_id = "test_client_id"
    google_client_secret = "test_client_secret"
    google_redirect_uri = "http://test-redirect"


@patch("app.services.drive.get_secrets", return_value=FakeSecrets())
def test_get_auth_url(mock_get_secrets):
    url = get_auth_url()

    parsed = urlparse(url)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/auth"

    query_params = parse_qs(parsed.query)

    assert query_params.get("client_id") == ["test_client_id"]
    assert query_params.get("redirect_uri") == ["http://test-redirect"]
    assert query_params.get("access_type") == ["offline"]
    assert query_params.get("prompt") == ["consent"]
    assert query_params.get("include_granted_scopes") == ["true"]
    assert query_params.get("response_type") == ["code"]

    scopes = query_params.get("scope", [""])[0].split()
    for expected_scope in SCOPES:
        assert expected_scope in scopes
