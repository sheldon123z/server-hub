"""Fleet 批量任务执行引擎 — parallel / serial / rolling 三策略"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from database import get_db
from modules.agents.stream_bridge import get_stream_bridge

logger = logging.getLogger(__name__)


class BatchExecutor:
    """批量任务执行引擎

    单例模式，由 get_batch_executor() 获取。
    内部维护运行中的 asyncio.Task 映射，支持取消。
    """

    def __init__(self):
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._cancelled_jobs: set[str] = set()

    async def submit(self, job_id: str) -> None:
        """异步提交任务到后台执行（立即返回）"""
        task = asyncio.create_task(self._run(job_id), name=f"batch-{job_id}")
        self._running_tasks[job_id] = task
        task.add_done_callback(lambda _t: self._running_tasks.pop(job_id, None))

    async def cancel(self, job_id: str) -> bool:
        """取消正在运行的任务"""
        self._cancelled_jobs.add(job_id)
        task = self._running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled_jobs

    # ─── 主执行流程 ───

    async def _run(self, job_id: str) -> None:
        """拉取任务信息并按策略分发执行"""
        db = await get_db()
        cursor = await db.execute("SELECT * FROM batch_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            logger.error("批量任务 %s 不存在", job_id)
            return

        job = dict(row)
        job["payload"] = json.loads(job["payload"])
        job["server_ids"] = json.loads(job["server_ids"])
        job["stop_on_failure"] = bool(job.get("stop_on_failure", 0))

        total = len(job["server_ids"])
        bridge = get_stream_bridge()

        # 更新状态为 running
        await db.execute(
            "UPDATE batch_jobs SET status = 'running', progress = ? WHERE id = ?",
            (json.dumps({"total": total, "completed": 0, "failed": 0, "running": total}), job_id),
        )
        await db.commit()

        await bridge.publish(
            job_id,
            "progress",
            json.dumps({"status": "running", "total": total, "completed": 0, "failed": 0, "running": total}),
        )

        try:
            strategy = job.get("strategy", "parallel")
            if strategy == "parallel":
                await self._parallel(job)
            elif strategy == "serial":
                await self._serial(job)
            elif strategy == "rolling":
                batch_size = max(1, job.get("rolling_batch_size") or 1)
                await self._rolling(job, batch_size)
            else:
                logger.warning("未知策略 %s，降级为 parallel", strategy)
                await self._parallel(job)
        except asyncio.CancelledError:
            logger.info("批量任务 %s 被取消", job_id)
        except Exception:
            logger.exception("批量任务 %s 执行异常", job_id)
        finally:
            await self._finalize(job_id, total, job["name"])

    async def _finalize(self, job_id: str, total: int, job_name: str) -> None:
        """统计结果，更新最终状态，发布 done 事件，发送通知"""
        db = await get_db()
        bridge = get_stream_bridge()

        if self.is_cancelled(job_id):
            final_status = "cancelled"
            completed = 0
            failed = 0
        else:
            cursor = await db.execute(
                "SELECT status, COUNT(*) FROM batch_job_results WHERE job_id = ? GROUP BY status",
                (job_id,),
            )
            rows = await cursor.fetchall()
            counts = {r[0]: r[1] for r in rows}
            completed = counts.get("success", 0)
            failed = counts.get("failed", 0)

            if failed == 0:
                final_status = "completed"
            elif completed > 0:
                final_status = "partial_failure"
            else:
                final_status = "failed"

        now = datetime.now(UTC).isoformat()
        progress = json.dumps({"total": total, "completed": completed, "failed": failed, "running": 0})
        await db.execute(
            "UPDATE batch_jobs SET status = ?, completed_at = ?, progress = ? WHERE id = ?",
            (final_status, now, progress, job_id),
        )
        await db.commit()

        await bridge.publish(
            job_id,
            "done",
            json.dumps({"status": final_status, "total": total, "completed": completed, "failed": failed}),
        )
        await bridge.publish_end(job_id)

        # 发送通知（非阻塞，存储引用避免 RUF006）
        _notify_task = asyncio.create_task(
            self._notify_completion(job_id, job_name, final_status, total, completed, failed)
        )
        _notify_task.add_done_callback(lambda _t: None)  # 防止 GC 回收

    # ─── 执行策略 ───

    async def _parallel(self, job: dict) -> None:
        """并行在所有服务器上执行"""
        await asyncio.gather(
            *[self._execute_on_server(job, sid) for sid in job["server_ids"]],
            return_exceptions=True,
        )

    async def _serial(self, job: dict) -> None:
        """逐台串行执行，支持 stop_on_failure"""
        for server_id in job["server_ids"]:
            if self.is_cancelled(job["id"]):
                break
            result = await self._execute_on_server(job, server_id)
            if job["stop_on_failure"] and isinstance(result, dict) and result.get("status") == "failed":
                logger.info("批量任务 %s: %s 失败，stop_on_failure=true，停止", job["id"], server_id)
                break

    async def _rolling(self, job: dict, batch_size: int) -> None:
        """分批并行执行，支持 stop_on_failure"""
        server_ids = job["server_ids"]
        for i in range(0, len(server_ids), batch_size):
            if self.is_cancelled(job["id"]):
                break
            batch = server_ids[i : i + batch_size]
            results = await asyncio.gather(
                *[self._execute_on_server(job, sid) for sid in batch],
                return_exceptions=True,
            )
            if job["stop_on_failure"]:
                has_failure = any(
                    isinstance(r, Exception) or (isinstance(r, dict) and r.get("status") == "failed") for r in results
                )
                if has_failure:
                    logger.info("批量任务 %s: 批次包含失败，stop_on_failure=true，停止", job["id"])
                    break

    # ─── 单服务器执行 ───

    async def _execute_on_server(self, job: dict, server_id: str) -> dict:
        """在单台服务器上执行，写 DB 结果并发布进度事件"""
        job_id = job["id"]
        started_at = datetime.now(UTC)
        bridge = get_stream_bridge()

        await bridge.publish(
            job_id,
            "server_start",
            json.dumps({"server_id": server_id, "started_at": started_at.isoformat()}),
        )

        try:
            if server_id == "local":
                result = await self._run_local(job)
            else:
                result = await self._run_remote(job, server_id)
        except Exception as e:
            result = {"status": "failed", "output": None, "error": str(e)}

        completed_at = datetime.now(UTC)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        db = await get_db()
        await db.execute(
            """INSERT INTO batch_job_results
               (job_id, server_id, status, output, error, started_at, completed_at, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                server_id,
                result["status"],
                result.get("output"),
                result.get("error"),
                started_at.isoformat(),
                completed_at.isoformat(),
                duration_ms,
            ),
        )

        # 更新进度计数
        cursor = await db.execute("SELECT COUNT(*) FROM batch_job_results WHERE job_id = ?", (job_id,))
        total_done = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM batch_job_results WHERE job_id = ? AND status = 'failed'", (job_id,)
        )
        failed_count = (await cursor.fetchone())[0]

        total = len(job["server_ids"])
        progress = {
            "total": total,
            "completed": total_done,
            "failed": failed_count,
            "running": max(0, total - total_done),
        }
        await db.execute(
            "UPDATE batch_jobs SET progress = ? WHERE id = ?",
            (json.dumps(progress), job_id),
        )
        await db.commit()

        await bridge.publish(
            job_id,
            "server_result",
            json.dumps(
                {
                    "server_id": server_id,
                    "status": result["status"],
                    "output": result.get("output"),
                    "error": result.get("error"),
                    "duration_ms": duration_ms,
                    "progress": progress,
                }
            ),
        )

        return result

    # ─── 本机执行 ───

    async def _run_local(self, job: dict) -> dict:
        """在本机以 subprocess 执行任务"""
        job_type = job["type"]
        payload = job["payload"]

        if job_type == "command":
            return await self._subprocess(payload.get("command", ""), timeout=int(payload.get("timeout", 30)))

        if job_type == "service_action":
            name = payload.get("name", "")
            action = payload.get("action", "status")
            return await self._subprocess(f"systemctl {action} {name}", timeout=30)

        if job_type == "docker_action":
            action = payload.get("action", "ps")
            name = payload.get("name", "")
            if action == "prune":
                return await self._subprocess("docker system prune -f", timeout=120)
            return await self._subprocess(f"docker {action} {name}", timeout=60)

        if job_type == "script":
            script_path = payload.get("script_path", "")
            args = payload.get("args", "")
            cmd = f"bash {script_path} {args}".strip() if args else f"bash {script_path}"
            return await self._subprocess(cmd, timeout=int(payload.get("timeout", 120)))

        if job_type == "playbook":
            return {"status": "failed", "output": None, "error": "本机暂不支持剧本类批量操作"}

        return {"status": "failed", "output": None, "error": f"未知任务类型: {job_type}"}

    async def _subprocess(self, cmd: str, timeout: int = 30) -> dict:  # noqa: ASYNC109
        """执行 shell 命令，返回统一结果结构"""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=float(timeout))
            except TimeoutError:
                proc.kill()
                return {"status": "failed", "output": None, "error": f"命令超时 ({timeout}s)"}

            out = stdout.decode("utf-8", errors="replace").strip()
            err = stderr.decode("utf-8", errors="replace").strip()
            if proc.returncode == 0:
                return {"status": "success", "output": out or err or "(无输出)", "error": None}
            return {"status": "failed", "output": out, "error": err or f"退出码 {proc.returncode}"}
        except Exception as e:
            return {"status": "failed", "output": None, "error": str(e)}

    # ─── 远程执行 ───

    async def _run_remote(self, job: dict, server_id: str) -> dict:
        """通过 AgentClient 在远程服务器上执行任务"""
        from modules.servers.agent_client import get_agent_client

        try:
            client = await get_agent_client(server_id)
        except ValueError as e:
            return {"status": "failed", "output": None, "error": str(e)}

        job_type = job["type"]
        payload = job["payload"]

        try:
            if job_type == "command":
                resp = await client.execute_command(payload.get("command", ""), timeout=int(payload.get("timeout", 30)))
            elif job_type == "service_action":
                resp = await client.service_action(payload.get("name", ""), payload.get("action", "status"))
            elif job_type == "docker_action":
                action = payload.get("action", "ps")
                if action == "prune":
                    resp = await client.execute_command("docker system prune -f", timeout=120)
                else:
                    resp = await client.docker_action(payload.get("name", ""), action)
            elif job_type == "script":
                script_path = payload.get("script_path", "")
                args = payload.get("args", "")
                cmd = f"bash {script_path} {args}".strip() if args else f"bash {script_path}"
                resp = await client.execute_command(cmd, timeout=int(payload.get("timeout", 120)))
            else:
                return {"status": "failed", "output": None, "error": f"未知任务类型: {job_type}"}
        except Exception as e:
            return {"status": "failed", "output": None, "error": str(e)}

        if not resp.get("ok"):
            return {"status": "failed", "output": None, "error": resp.get("error", "Agent 返回错误")}

        data = resp.get("data", {})
        output = data.get("stdout") or data.get("output") or ""
        stderr = data.get("stderr") or ""
        retcode = data.get("returncode", 0)

        if retcode != 0:
            return {"status": "failed", "output": output, "error": stderr or f"退出码 {retcode}"}
        return {"status": "success", "output": output or stderr or "(无输出)", "error": None}

    # ─── 通知 ───

    async def _notify_completion(
        self,
        job_id: str,
        job_name: str,
        status: str,
        total: int,
        completed: int,
        failed: int,
    ) -> None:
        try:
            from modules.notifications.dispatcher import dispatch

            severity = "info" if status == "completed" else "warning"
            title = f"批量任务完成: {job_name}"
            content = f"状态: {status} | 总计: {total} | 成功: {completed} | 失败: {failed} | 任务ID: {job_id}"
            await dispatch(title=title, content=content, severity=severity, type="batch_job")
        except Exception:
            logger.debug("批量任务通知发送失败 (非关键错误)", exc_info=True)


# ─── 全局单例 ───

_executor: BatchExecutor | None = None


def get_batch_executor() -> BatchExecutor:
    """获取全局 BatchExecutor 单例"""
    global _executor
    if _executor is None:
        _executor = BatchExecutor()
    return _executor
