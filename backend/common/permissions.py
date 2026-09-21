from django.conf import settings
from rest_framework.permissions import BasePermission


def _in_group(user, group_name):
    return user.is_authenticated and user.groups.filter(name=group_name).exists()


class IsDataTeam(BasePermission):
    """Admin/Data Team only — full edit rights, imports, user management."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and (user.is_superuser or _in_group(user, settings.DATA_TEAM_GROUP)))


class IsRegulatorOrAbove(BasePermission):
    """Regulator or Data Team — Site Check access, propose registry edits."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_superuser
            or _in_group(user, settings.DATA_TEAM_GROUP)
            or _in_group(user, settings.REGULATOR_GROUP)
        )
