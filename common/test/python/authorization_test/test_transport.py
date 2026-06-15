"""Unit tests for SigV4Transport signing.

Task 7.3: Test that SigV4Transport produces valid Authorization headers.
Uses moto for credential mocking.

Requirements: 1.4
"""

import json
from unittest.mock import patch
from urllib.parse import urlparse

from authorization.sigv4_transport import SigV4Transport
from moto import mock_aws


@mock_aws
class TestSigV4TransportSigning:
    """Tests for SigV4Transport request signing.

    Validates: Requirement 1.4
    """

    def _create_transport(
        self, base_url: str = "https://api.example.com/v1"
    ) -> SigV4Transport:
        """Create a SigV4Transport with mocked AWS credentials."""
        with patch.dict(
            "os.environ",
            {
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "AWS_DEFAULT_REGION": "us-east-1",
            },
        ):
            return SigV4Transport(base_url=base_url, region="us-east-1")

    def test_request_includes_authorization_header(self) -> None:
        """SigV4Transport produces an Authorization header on requests.

        Validates: Requirement 1.4
        """
        transport = self._create_transport()

        # Patch urlopen to capture the signed request
        with patch("urllib.request.urlopen") as mock_urlopen:
            # Set up mock response
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "healthy"}'

            transport.request(method="GET", path="/health", body=None)

            # Get the Request object passed to urlopen
            call_args = mock_urlopen.call_args
            request_obj = call_args[0][0]

            # Verify Authorization header is present
            auth_header = request_obj.get_header("Authorization")
            assert auth_header is not None
            assert "AWS4-HMAC-SHA256" in auth_header

    def test_authorization_header_contains_credential(self) -> None:
        """Authorization header contains Credential component."""
        transport = self._create_transport()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="GET", path="/health", body=None)

            request_obj = mock_urlopen.call_args[0][0]
            auth_header = request_obj.get_header("Authorization")
            assert "Credential=" in auth_header

    def test_authorization_header_contains_signed_headers(self) -> None:
        """Authorization header contains SignedHeaders component."""
        transport = self._create_transport()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="GET", path="/health", body=None)

            request_obj = mock_urlopen.call_args[0][0]
            auth_header = request_obj.get_header("Authorization")
            assert "SignedHeaders=" in auth_header

    def test_authorization_header_contains_signature(self) -> None:
        """Authorization header contains Signature component."""
        transport = self._create_transport()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="GET", path="/health", body=None)

            request_obj = mock_urlopen.call_args[0][0]
            auth_header = request_obj.get_header("Authorization")
            assert "Signature=" in auth_header

    def test_signs_against_execute_api_service(self) -> None:
        """SigV4 signing uses 'execute-api' as the service name.

        Validates: Requirement 1.4
        """
        transport = self._create_transport()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="GET", path="/health", body=None)

            request_obj = mock_urlopen.call_args[0][0]
            auth_header = request_obj.get_header("Authorization")
            # Credential format: AKID/date/region/service/aws4_request
            assert "execute-api" in auth_header

    def test_post_request_includes_content_type(self) -> None:
        """POST requests with body include Content-Type header."""
        transport = self._create_transport()
        body = json.dumps({"key": "value"}).encode()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="POST", path="/grants", body=body)

            request_obj = mock_urlopen.call_args[0][0]
            content_type = request_obj.get_header("Content-type")
            assert content_type == "application/json"

    def test_constructs_correct_url(self) -> None:
        """Transport constructs the full URL from base_url and path."""
        transport = self._create_transport(base_url="https://api.example.com/v1")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="GET", path="/health", body=None)

            request_obj = mock_urlopen.call_args[0][0]
            assert request_obj.full_url == "https://api.example.com/v1/health"

    def test_constructs_url_with_query_params(self) -> None:
        """Transport appends query parameters to the URL."""
        transport = self._create_transport(base_url="https://api.example.com/v1")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(
                method="GET",
                path="/users/user1/permissions",
                body=None,
                query_params={"type": "study", "relation": "member"},
            )

            request_obj = mock_urlopen.call_args[0][0]
            parsed = urlparse(request_obj.full_url)
            assert "type=study" in parsed.query
            assert "relation=member" in parsed.query

    def test_uses_correct_http_method(self) -> None:
        """Transport uses the specified HTTP method."""
        transport = self._create_transport()

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = mock_urlopen.return_value.__enter__.return_value
            mock_response.status = 200
            mock_response.read.return_value = b"{}"

            transport.request(method="DELETE", path="/grants", body=b"{}")

            request_obj = mock_urlopen.call_args[0][0]
            assert request_obj.method == "DELETE"

    def test_different_requests_produce_different_signatures(self) -> None:
        """Different request bodies produce different signatures."""
        transport = self._create_transport()

        signatures = []
        for i in range(2):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_response = mock_urlopen.return_value.__enter__.return_value
                mock_response.status = 200
                mock_response.read.return_value = b"{}"

                body = json.dumps({"userId": f"user{i}"}).encode()
                transport.request(method="POST", path="/grants", body=body)

                request_obj = mock_urlopen.call_args[0][0]
                auth_header = request_obj.get_header("Authorization")
                # Extract signature value
                sig_part = next(
                    p.strip() for p in auth_header.split(",") if "Signature=" in p
                )
                signatures.append(sig_part)

        # Different payloads should produce different signatures
        assert signatures[0] != signatures[1]
