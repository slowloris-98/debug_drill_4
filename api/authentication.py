"""API-key authentication.

Customers and their grading partners call the public API with

    Authorization: Api-Key <key>

A key that is missing, unknown, or revoked is rejected with 401 and a
`WWW-Authenticate` header naming the scheme.
"""

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from core.models import ApiKey

KEYWORD = "Api-Key"


class ApiKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].decode().lower() != KEYWORD.lower():
            return None
        if len(header) != 2:
            raise AuthenticationFailed("Malformed Authorization header.")

        presented = header[1].decode()
        try:
            api_key = ApiKey.objects.select_related("organization").get(key=presented)
        except ApiKey.DoesNotExist:
            raise AuthenticationFailed("Unknown API key.")

        if api_key.revoked_at is not None:
            raise AuthenticationFailed("This API key has been revoked.")

        return (api_key.organization.owner, api_key)

    def authenticate_header(self, request):
        return f'{KEYWORD} realm="api"'
