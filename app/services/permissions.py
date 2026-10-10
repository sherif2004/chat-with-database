USER = "user"
SUPERVISOR = "supervisor"
ADMIN = "admin"

ROLES = (USER, SUPERVISOR, ADMIN)

_USER_PERMISSIONS = frozenset({"chat", "conversation:own"})
_SUPERVISOR_PERMISSIONS = _USER_PERMISSIONS | {
    "connection:write",
    "conversation:read_any",
    "users:read",
}
_ADMIN_PERMISSIONS = _SUPERVISOR_PERMISSIONS | {"users:write", "data:write"}

# The single source of truth for what each role may do. Routes ask for a
# permission by name; nothing else in the app should compare role strings.
PERMISSIONS: dict[str, frozenset[str]] = {
    USER: _USER_PERMISSIONS,
    SUPERVISOR: frozenset(_SUPERVISOR_PERMISSIONS),
    ADMIN: frozenset(_ADMIN_PERMISSIONS),
}


def permissions_for(role: str) -> frozenset[str]:
    return PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)
