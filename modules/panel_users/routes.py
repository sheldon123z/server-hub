"""Panel user management API routes."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import user_store
from auth.dependencies import require_role

router = APIRouter(prefix="/api/panel-users", tags=["面板用户"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field("", max_length=64)
    role: str = Field("user", pattern=r"^(admin|user)$")


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(None, max_length=64)
    role: str | None = Field(None, pattern=r"^(admin|user)$")
    disabled: bool | None = None
    password: str | None = Field(None, min_length=6, max_length=128)


@router.get("/")
async def list_users(user=Depends(require_role("admin"))):
    """List all panel users."""
    try:
        users = await user_store.list_users()
        return {"users": users, "count": len(users)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_user(
    body: CreateUserRequest,
    user=Depends(require_role("admin")),
):
    """Create a new panel user."""
    try:
        new_user = await user_store.create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
        )
        return new_user
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    user=Depends(require_role("admin")),
):
    """Update an existing panel user's properties."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = await user_store.update_user(int(user_id), **updates)
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    user=Depends(require_role("admin")),
):
    """Delete a panel user. Cannot delete yourself."""
    # Prevent self-deletion
    current_user_id = (
        getattr(user, "id", None) or user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
    )
    if str(current_user_id) == str(user_id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    try:
        await user_store.delete_user(int(user_id))
        return {"ok": True, "deleted_user_id": user_id}
    except KeyError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
