"""Agent Skills 管理与推荐路由。"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from auth.dependencies import get_current_user, require_role
from modules.agents.schemas import InstallFromRepoRequest, SkillSourceUpdate
from modules.agents.skill_service import (
    discover_skills,
    get_skill,
    get_skill_sources,
    install_skill_from_repo,
    install_skill_from_upload,
    list_skills,
    recommend_skills,
    remove_skill,
    save_skill_sources,
    set_skill_enabled,
)

router = APIRouter()


@router.get("/admin/skills")
async def list_agent_skills(user=Depends(require_role("admin"))):
    return {"skills": await list_skills()}


@router.get("/admin/skill-sources")
async def list_skill_sources(user=Depends(require_role("admin"))):
    return {"roots": get_skill_sources()}


@router.put("/admin/skill-sources")
async def update_skill_sources(body: SkillSourceUpdate, user=Depends(require_role("admin"))):
    return {"roots": save_skill_sources(body.roots)}


@router.post("/admin/skills/discover")
async def discover_agent_skills(user=Depends(require_role("admin"))):
    return {"items": await discover_skills()}


@router.post("/admin/skills/install-from-repo")
async def install_agent_skill_from_repo(body: InstallFromRepoRequest, user=Depends(require_role("admin"))):
    skill = await install_skill_from_repo(body.repo_path, created_by=user["username"])
    return {"ok": True, "skill": skill}


@router.post("/admin/skills/install-upload")
async def install_agent_skill_upload(
    file: UploadFile = File(...),
    user=Depends(require_role("admin")),
):
    content = await file.read()
    skill = await install_skill_from_upload(file.filename or "skill.zip", content, created_by=user["username"])
    return {"ok": True, "skill": skill}


@router.post("/admin/skills/{skill_id}/enable")
async def enable_agent_skill(skill_id: str, user=Depends(require_role("admin"))):
    await set_skill_enabled(skill_id, True, created_by=user["username"])
    return {"ok": True}


@router.post("/admin/skills/{skill_id}/disable")
async def disable_agent_skill(skill_id: str, user=Depends(require_role("admin"))):
    await set_skill_enabled(skill_id, False, created_by=user["username"])
    return {"ok": True}


@router.delete("/admin/skills/{skill_id}")
async def delete_agent_skill(skill_id: str, user=Depends(require_role("admin"))):
    ok = await remove_skill(skill_id, created_by=user["username"])
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True}


@router.get("/skills/{skill_id}")
async def get_agent_skill(skill_id: str, user=Depends(get_current_user)):
    skill = await get_skill(skill_id, include_content=True)
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    allowed = skill["manifest"].get("allowed_roles", ["admin", "user"])
    if user["role"] not in allowed:
        raise HTTPException(status_code=403, detail="无权查看此技能")
    return skill


@router.get("/skills/recommendations")
async def get_skill_recommendations(
    message: str = "",
    page_context: str | None = None,
    user=Depends(get_current_user),
):
    return {
        "items": await recommend_skills(
            message=message,
            page_context=page_context,
            user_role=user["role"],
        )
    }
