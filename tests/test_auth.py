"""Auth 模块测试 — 登录/登出、JWT 令牌、角色校验、Cookie 认证"""

import os
import sys
from datetime import UTC, datetime, timedelta

import aiosqlite
import httpx
import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="session")
async def auth_db():
    """初始化内存数据库，创建 panel_users 表并插入测试用户"""
    import database
    from auth.user_store import hash_password

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    database._db = db
    await database.init_tables(db)

    # 插入测试管理员
    await db.execute(
        "INSERT INTO panel_users (username, hashed_password, display_name, role, token_version) VALUES (?, ?, ?, ?, ?)",
        ("testadmin", hash_password("admin123"), "测试管理员", "admin", 0),
    )
    # 插入普通用户
    await db.execute(
        "INSERT INTO panel_users (username, hashed_password, display_name, role, token_version) VALUES (?, ?, ?, ?, ?)",
        ("testuser", hash_password("user123"), "测试用户", "user", 0),
    )
    # 插入已禁用用户
    await db.execute(
        "INSERT INTO panel_users (username, hashed_password, display_name, role, disabled, token_version) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("disableduser", hash_password("disabled123"), "已禁用", "user", 1, 0),
    )
    await db.commit()
    yield db
    await db.close()
    database._db = None


@pytest_asyncio.fixture
async def client(auth_db):
    """创建 httpx AsyncClient，挂载 auth 路由"""
    from auth.routes import router

    app = FastAPI()
    app.include_router(router)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def protected_client(auth_db):
    """创建包含需要认证端点的 AsyncClient"""
    from auth.routes import router

    app = FastAPI()
    app.include_router(router)

    # 清除速率限制状态
    from auth.routes import _login_attempts

    _login_attempts.clear()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# 1. 登录测试
# ═══════════════════════════════════════════════════════════════════════════


class TestLogin:
    async def test_valid_admin_login(self, client):
        """有效管理员凭证登录返回 200 + set-cookie"""
        from auth.routes import _login_attempts

        _login_attempts.clear()
        resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["user"]["username"] == "testadmin"
        assert data["user"]["role"] == "admin"
        # 检查 cookie 是否设置
        assert "access_token" in resp.cookies or any("access_token" in h for h in resp.headers.get_list("set-cookie"))

    async def test_valid_user_login(self, client):
        """普通用户登录"""
        from auth.routes import _login_attempts

        _login_attempts.clear()
        resp = await client.post("/api/auth/login", json={"username": "testuser", "password": "user123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["user"]["role"] == "user"

    async def test_invalid_password(self, client):
        """无效密码返回 401"""
        from auth.routes import _login_attempts

        _login_attempts.clear()
        resp = await client.post("/api/auth/login", json={"username": "testadmin", "password": "wrongpassword"})
        assert resp.status_code == 401

    async def test_nonexistent_user(self, client):
        """不存在的用户返回 401"""
        from auth.routes import _login_attempts

        _login_attempts.clear()
        resp = await client.post("/api/auth/login", json={"username": "nobody", "password": "anything"})
        assert resp.status_code == 401

    async def test_disabled_user_login(self, client):
        """已禁用用户登录返回 401"""
        from auth.routes import _login_attempts

        _login_attempts.clear()
        resp = await client.post("/api/auth/login", json={"username": "disableduser", "password": "disabled123"})
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 2. JWT Token 测试
# ═══════════════════════════════════════════════════════════════════════════


class TestJWTToken:
    def test_create_and_verify_access_token(self):
        """创建 access token 并验证"""
        from auth.jwt_handler import create_access_token, verify_token

        token = create_access_token("testadmin", "admin", 0)
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "testadmin"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"
        assert payload["ver"] == 0

    def test_create_and_verify_refresh_token(self):
        """创建 refresh token 并验证"""
        from auth.jwt_handler import create_refresh_token, verify_token

        token = create_refresh_token("testuser", 0)
        payload = verify_token(token)
        assert payload is not None
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_expired_token_returns_none(self):
        """过期 token 验证返回 None"""
        from config import settings

        expire = datetime.now(UTC) - timedelta(seconds=10)
        payload = {
            "sub": "testadmin",
            "role": "admin",
            "exp": expire,
            "type": "access",
            "ver": 0,
            "jti": "test-jti",
        }
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

        from auth.jwt_handler import verify_token

        result = verify_token(token)
        assert result is None

    def test_invalid_token_returns_none(self):
        """无效 token 返回 None"""
        from auth.jwt_handler import verify_token

        result = verify_token("this.is.not.valid")
        assert result is None

    def test_wrong_secret_returns_none(self):
        """使用错误密钥签名的 token 返回 None"""
        from auth.jwt_handler import verify_token

        payload = {
            "sub": "testadmin",
            "role": "admin",
            "exp": datetime.now(UTC) + timedelta(hours=1),
            "type": "access",
            "ver": 0,
        }
        token = jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        result = verify_token(token)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Token 刷新测试
# ═══════════════════════════════════════════════════════════════════════════


class TestTokenRefresh:
    async def test_refresh_with_valid_token(self, protected_client):
        """有效 refresh token 可刷新 access token"""
        from auth.jwt_handler import create_refresh_token

        refresh_token = create_refresh_token("testadmin", 0)
        # 设置 refresh_token cookie
        protected_client.cookies.set("refresh_token", refresh_token)
        resp = await protected_client.post("/api/auth/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    async def test_refresh_without_token(self, protected_client):
        """无 refresh token 返回 401"""
        protected_client.cookies.clear()
        resp = await protected_client.post("/api/auth/refresh")
        assert resp.status_code == 401

    async def test_refresh_with_expired_token(self, protected_client):
        """过期 refresh token 返回 401"""
        from config import settings

        expire = datetime.now(UTC) - timedelta(seconds=10)
        payload = {"sub": "testadmin", "exp": expire, "type": "refresh", "ver": 0, "jti": "expired"}
        token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

        protected_client.cookies.set("refresh_token", token)
        resp = await protected_client.post("/api/auth/refresh")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 4. 角色权限测试
# ═══════════════════════════════════════════════════════════════════════════


class TestRoleAuthorization:
    async def test_require_role_admin_allows_admin(self, auth_db):
        """require_role("admin") 允许 admin 角色"""
        from auth.dependencies import require_role
        from auth.jwt_handler import create_access_token

        app = FastAPI()

        @app.get("/admin-only")
        async def admin_only(user=fastapi_depends(require_role("admin"))):
            return {"ok": True}

        token = create_access_token("testadmin", "admin", 0)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.cookies.set("access_token", token)
            resp = await c.get("/admin-only")
            assert resp.status_code == 200

    async def test_require_role_admin_rejects_user(self, auth_db):
        """require_role("admin") 拒绝 user 角色"""
        from auth.dependencies import require_role
        from auth.jwt_handler import create_access_token

        app = FastAPI()

        @app.get("/admin-only")
        async def admin_only(user=fastapi_depends(require_role("admin"))):
            return {"ok": True}

        token = create_access_token("testuser", "user", 0)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.cookies.set("access_token", token)
            resp = await c.get("/admin-only")
            assert resp.status_code == 403

    async def test_no_token_returns_401(self, auth_db):
        """未登录访问保护端点返回 401"""
        from auth.routes import router

        app = FastAPI()
        app.include_router(router)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/auth/me")
            assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 5. /me 端点测试
# ═══════════════════════════════════════════════════════════════════════════


class TestMeEndpoint:
    async def test_me_with_valid_token(self, protected_client):
        """有效 token 访问 /me 返回用户信息"""
        from auth.jwt_handler import create_access_token

        token = create_access_token("testadmin", "admin", 0)
        protected_client.cookies.set("access_token", token)
        resp = await protected_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testadmin"
        assert data["role"] == "admin"

    async def test_me_without_token(self, protected_client):
        """无 token 访问 /me 返回 401"""
        protected_client.cookies.clear()
        resp = await protected_client.get("/api/auth/me")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# 6. 登出测试
# ═══════════════════════════════════════════════════════════════════════════


class TestLogout:
    async def test_logout_clears_cookies(self, protected_client):
        """登出返回 200"""
        resp = await protected_client.post("/api/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 7. 用户存储层测试
# ═══════════════════════════════════════════════════════════════════════════


class TestUserStore:
    async def test_authenticate_valid(self, auth_db):
        """authenticate 函数验证有效凭证"""
        from auth.user_store import authenticate

        user = await authenticate("testadmin", "admin123")
        assert user is not None
        assert user["username"] == "testadmin"
        assert user["role"] == "admin"

    async def test_authenticate_wrong_password(self, auth_db):
        """authenticate 函数拒绝错误密码"""
        from auth.user_store import authenticate

        user = await authenticate("testadmin", "wrongpassword")
        assert user is None

    async def test_authenticate_nonexistent(self, auth_db):
        """authenticate 函数拒绝不存在的用户"""
        from auth.user_store import authenticate

        user = await authenticate("nonexistent", "password")
        assert user is None

    async def test_get_user_by_name(self, auth_db):
        """get_user_by_name 返回用户"""
        from auth.user_store import get_user_by_name

        user = await get_user_by_name("testadmin")
        assert user is not None
        assert user["username"] == "testadmin"

    async def test_get_user_by_name_nonexistent(self, auth_db):
        """get_user_by_name 不存在返回 None"""
        from auth.user_store import get_user_by_name

        user = await get_user_by_name("nobody")
        assert user is None

    async def test_password_hash_verify(self, auth_db):
        """hash_password + verify_password 往返验证"""
        from auth.user_store import hash_password, verify_password

        hashed = hash_password("my_password_123")
        assert hashed != "my_password_123"
        assert verify_password("my_password_123", hashed) is True
        assert verify_password("wrong_password", hashed) is False

    async def test_token_version_tracking(self, auth_db):
        """get_token_version 返回正确版本号"""
        from auth.user_store import get_token_version

        version = get_token_version({"token_version": 5})
        assert version == 5

        version = get_token_version({"token_version": None})
        assert version == 0

        version = get_token_version(None)
        assert version == 0


# ─── 辅助 ───

from fastapi import Depends as fastapi_depends  # noqa: E402
