"""Agent Skills 管理与推荐路由。"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from auth.dependencies import get_current_user, require_role
from modules.agents.schemas import (
    EvalRunRequest,
    InstallFromRepoRequest,
    MarketInstallRequest,
    RollbackRequest,
    SkillCreate,
    SkillFileUpload,
    SkillSourceUpdate,
    SkillUpdate,
)
from modules.agents.skill_service import (
    create_skill,
    delete_skill_file,
    discover_skills,
    export_skill_zip,
    get_skill,
    get_skill_eval_results,
    get_skill_evals,
    get_skill_files,
    get_skill_sources,
    get_skill_versions,
    install_skill_from_repo,
    install_skill_from_upload,
    list_enabled_skills,
    list_skills,
    recommend_skills,
    remove_skill,
    rollback_skill,
    run_skill_eval,
    save_skill_evals,
    save_skill_sources,
    set_skill_enabled,
    update_skill,
    upload_skill_file,
)

logger = logging.getLogger(__name__)

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


@router.get("/skills/list")
async def list_enabled_agent_skills(user=Depends(get_current_user)):
    """返回 enabled 技能的 name+description（给 /skill: 菜单，需登录但不需 admin）。"""
    return {"items": await list_enabled_skills(user_role=user["role"])}


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


# ---------------------------------------------------------------------------
# 技能 CRUD（管理员）
# ---------------------------------------------------------------------------


@router.post("/admin/skills/create")
async def create_agent_skill(body: SkillCreate, user=Depends(require_role("admin"))):
    """创建新技能。"""
    skill = await create_skill(
        name=body.name,
        skill_md=body.skill_md,
        files=body.files,
        created_by=user["username"],
    )
    return {"ok": True, "skill": skill}


@router.put("/admin/skills/{skill_id}")
async def update_agent_skill(skill_id: str, body: SkillUpdate, user=Depends(require_role("admin"))):
    """更新技能 SKILL.md 和/或附属文件。"""
    skill = await update_skill(
        skill_id=skill_id,
        skill_md=body.skill_md,
        files=body.files,
        updated_by=user["username"],
    )
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, "skill": skill}


# ---------------------------------------------------------------------------
# 附属文件管理（管理员）
# ---------------------------------------------------------------------------


@router.get("/admin/skills/{skill_id}/files")
async def list_skill_files(skill_id: str, user=Depends(require_role("admin"))):
    """列出技能的附属文件。"""
    files = await get_skill_files(skill_id)
    if files is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"files": files}


@router.put("/admin/skills/{skill_id}/files/{path:path}")
async def upload_agent_skill_file(
    skill_id: str,
    path: str,
    body: SkillFileUpload,
    user=Depends(require_role("admin")),
):
    """上传/更新技能附属文件。"""
    ok = await upload_skill_file(skill_id=skill_id, file_path=path, content=body.content)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True}


@router.delete("/admin/skills/{skill_id}/files/{path:path}")
async def delete_agent_skill_file(
    skill_id: str,
    path: str,
    user=Depends(require_role("admin")),
):
    """删除技能附属文件。"""
    ok = await delete_skill_file(skill_id=skill_id, file_path=path)
    if not ok:
        raise HTTPException(status_code=404, detail="技能或文件不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 导出（管理员）
# ---------------------------------------------------------------------------


@router.post("/admin/skills/{skill_id}/export")
async def export_agent_skill(skill_id: str, user=Depends(require_role("admin"))):
    """导出技能为 .zip 包（StreamingResponse）。"""
    result = await export_skill_zip(skill_id)
    if not result:
        raise HTTPException(status_code=404, detail="技能不存在")
    return StreamingResponse(
        result["stream"],
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )


# ---------------------------------------------------------------------------
# 版本管理（管理员）
# ---------------------------------------------------------------------------


@router.get("/admin/skills/{skill_id}/versions")
async def list_skill_version_history(skill_id: str, user=Depends(require_role("admin"))):
    """列出技能的版本快照。"""
    versions = await get_skill_versions(skill_id)
    if versions is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"versions": versions}


@router.post("/admin/skills/{skill_id}/rollback")
async def rollback_agent_skill(
    skill_id: str,
    body: RollbackRequest,
    user=Depends(require_role("admin")),
):
    """回滚技能到指定版本。"""
    ok = await rollback_skill(skill_id=skill_id, version=body.version, rolled_back_by=user["username"])
    if not ok:
        raise HTTPException(status_code=404, detail="技能或目标版本不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 技能市场（管理员）
# ---------------------------------------------------------------------------


@router.get("/admin/skill-market")
async def get_skill_market_index(user=Depends(require_role("admin"))):
    """获取市场索引（带本地安装状态对比）。"""
    try:
        from modules.agents.skill_market import get_market_index

        return {"items": await get_market_index()}
    except ImportError:
        logger.warning("skill_market 模块尚未实现")
        return {"items": []}


@router.post("/admin/skill-market/sync")
async def sync_skill_market(user=Depends(require_role("admin"))):
    """从远程拉取最新 registry。"""
    try:
        from modules.agents.skill_market import sync_market

        result = await sync_market()
        return {"ok": True, **result}
    except ImportError:
        logger.warning("skill_market 模块尚未实现")
        return {"ok": False, "error": "skill_market 模块尚未实现"}


@router.post("/admin/skill-market/install/{name}")
async def install_from_market(
    name: str,
    body: MarketInstallRequest | None = None,
    user=Depends(require_role("admin")),
):
    """从市场安装技能。"""
    version = body.version if body else None
    try:
        from modules.agents.skill_market import install_from_market as _install

        skill = await _install(name=name, version=version, installed_by=user["username"])
        return {"ok": True, "skill": skill}
    except ImportError:
        logger.warning("skill_market 模块尚未实现")
        raise HTTPException(status_code=501, detail="skill_market 模块尚未实现")


# ---------------------------------------------------------------------------
# 评测系统（管理员）
# ---------------------------------------------------------------------------


@router.get("/admin/skills/{skill_id}/evals")
async def get_agent_skill_evals(skill_id: str, user=Depends(require_role("admin"))):
    """获取技能评测用例集。"""
    evals = await get_skill_evals(skill_id)
    if evals is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"evals": evals}


@router.put("/admin/skills/{skill_id}/evals")
async def save_agent_skill_evals(skill_id: str, body: dict, user=Depends(require_role("admin"))):
    """保存技能评测用例集。"""
    ok = await save_skill_evals(skill_id=skill_id, evals_data=body)
    if not ok:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True}


@router.post("/admin/skills/{skill_id}/evals/run")
async def run_agent_skill_eval(
    skill_id: str,
    body: EvalRunRequest,
    user=Depends(require_role("admin")),
):
    """执行技能评测（异步）。"""
    result = await run_skill_eval(
        skill_id=skill_id,
        eval_id=body.eval_id,
        mode=body.mode,
        triggered_by=user["username"],
    )
    if not result:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, **result}


@router.get("/admin/skills/{skill_id}/evals/results")
async def get_agent_skill_eval_results(skill_id: str, user=Depends(require_role("admin"))):
    """获取技能评测结果列表。"""
    results = await get_skill_eval_results(skill_id)
    if results is None:
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"results": results}
