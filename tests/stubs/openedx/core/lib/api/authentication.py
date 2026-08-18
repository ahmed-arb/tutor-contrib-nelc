"""Stand-in for the platform's bearer authentication class."""

from rest_framework.authentication import BaseAuthentication


class BearerAuthenticationAllowInactiveUser(BaseAuthentication):
    def authenticate(self, request):
        return None
