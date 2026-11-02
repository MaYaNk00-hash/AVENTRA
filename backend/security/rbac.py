from typing import List
from fastapi import Depends, HTTPException, status
from backend.database.models import User
from backend.security.auth import get_current_user


class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if "ADMIN" == current_user.role:
            # Superadmin inherits all permissions
            return current_user
            
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {self.allowed_roles}, Your role: {current_user.role}"
            )
        return current_user


def require_roles(*roles: str):
    return RoleChecker(list(roles))

