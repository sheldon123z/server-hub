# 文件管理器 API

Web 文件管理器，支持浏览、读写、上传、下载、搜索文件，内置路径安全防护。

**路由前缀**: `/api/files`
**相关文件**: `modules/files/routes.py`, `modules/files/services.py`, `modules/files/security.py`

---

## 安全策略

### 允许访问的根目录（ALLOWED_ROOTS）

| 路径 | 用途 |
|------|------|
| `/home` | 用户主目录 |
| `/var/log` | 系统日志 |
| `/etc` | 系统配置（只读推荐） |
| `/tmp` | 临时文件 |
| `/opt` | 第三方应用 |
| `/mnt` | 挂载目录 |

请求访问 ALLOWED_ROOTS 以外的路径会返回 `403 Forbidden`。

### 受保护文件（PROTECTED_PATTERNS，禁止写操作）

- `**/passwd`, `**/shadow`, `**/sudoers` — 系统账户文件
- `**/.ssh/**` — SSH 密钥
- `**/.api_keys`, `**/.telegram_config` — 密钥配置
- `**/*.pem`, `**/*.key`, `**/*.p12` — 证书私钥
- `**/config.yaml`, `**/lobe.env` — 代理/服务配置

### 文件大小限制

| 操作 | 限制 |
|------|------|
| 文件读取（预览） | ≤ 5 MB |
| 文件上传 | ≤ 100 MB |
| 文件下载 | ≤ 500 MB |
| grep 搜索单个文件 | ≤ 10 MB（自动跳过更大文件） |

---

## 只读端点

### GET /api/files/list

列出目录内容。

**权限**: `files:read`

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 目录绝对路径 |
| sort | string | 否 | `name`(默认)/`size`/`mtime` |

**响应**:
```json
{
  "path": "/home/zhengxiaodong",
  "items": [
    {
      "name": "scripts",
      "path": "/home/zhengxiaodong/scripts",
      "is_dir": true,
      "size": 0,
      "mtime": "2026-04-01T12:00:00",
      "permissions": "drwxr-xr-x"
    },
    {
      "name": "readme.md",
      "path": "/home/zhengxiaodong/readme.md",
      "is_dir": false,
      "size": 1024,
      "mtime": "2026-03-20T08:30:00",
      "permissions": "-rw-r--r--"
    }
  ],
  "total": 2
}
```

---

### GET /api/files/read

读取文件内容（文本文件，≤5MB）。

**权限**: `files:read`

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件绝对路径 |

**响应**:
```json
{
  "path": "/var/log/nginx/access.log",
  "content": "127.0.0.1 - - [05/Apr/2026:10:30:00] ...",
  "size": 4096,
  "mime_type": "text/plain"
}
```

---

### GET /api/files/stat

获取文件或目录的元信息。

**权限**: `files:read`

**查询参数**: `path=<绝对路径>`

**响应**:
```json
{
  "path": "/home/zhengxiaodong/scripts",
  "name": "scripts",
  "is_dir": true,
  "is_file": false,
  "size": 0,
  "mtime": "2026-04-01T12:00:00",
  "ctime": "2025-12-01T08:00:00",
  "permissions": "drwxr-xr-x",
  "owner": "zhengxiaodong",
  "group": "zhengxiaodong"
}
```

---

### GET /api/files/search

按文件名搜索（支持 glob 通配符）。

**权限**: `files:read`

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 搜索起始目录 |
| query | string | 是 | 文件名关键字或 glob（如 `*.log`）|

**响应**:
```json
{
  "path": "/var/log",
  "query": "*.log",
  "results": [
    {"path": "/var/log/syslog", "name": "syslog", "size": 102400, "mtime": "..."},
    {"path": "/var/log/nginx/access.log", "name": "access.log", "size": 4096, "mtime": "..."}
  ],
  "total": 2
}
```

---

### GET /api/files/grep

在文件内容中搜索（正则 grep），跳过 >10MB 的文件。

**权限**: `files:read`

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 搜索起始路径（目录或文件） |
| pattern | string | 是 | 正则表达式（如 `ERROR.*timeout`） |

**响应**:
```json
{
  "path": "/var/log",
  "pattern": "ERROR",
  "results": [
    {
      "file": "/var/log/app.log",
      "line": 142,
      "content": "2026-04-05 10:30:00 ERROR Connection timeout"
    }
  ],
  "total": 1
}
```

---

### GET /api/files/download

下载文件（≤500MB），触发浏览器下载。

**权限**: `files:read`

**查询参数**: `path=<文件绝对路径>`

**响应**: 文件流（`Content-Disposition: attachment`），MIME 类型自动推断。

---

## 写操作端点

以下端点均需要 `files:write` 权限，并自动记录审计日志。

### PUT /api/files/write

写入/保存文件内容。目标文件不存在时自动创建，已存在时覆盖。

**权限**: `files:write`

**请求体**:
```json
{
  "path": "/home/zhengxiaodong/test.txt",
  "content": "文件内容..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 文件绝对路径（1~4096 字符） |
| content | string | 否 | 文件内容（默认为空） |

**响应**:
```json
{
  "ok": true,
  "path": "/home/zhengxiaodong/test.txt",
  "size": 1024
}
```

---

### POST /api/files/upload

上传文件到指定目录（≤100MB，`multipart/form-data`）。

**权限**: `files:write`

**查询参数**: `path=<目标目录绝对路径>`

**Form 字段**: `file`（二进制文件）

**响应**:
```json
{
  "ok": true,
  "path": "/home/zhengxiaodong/uploads/data.csv",
  "size": 204800,
  "filename": "data.csv"
}
```

---

### POST /api/files/action

执行文件系统操作（创建目录/重命名/复制/移动/删除）。

**权限**: `files:write`

**请求体**:
```json
{
  "action": "mkdir",
  "source": "/home/zhengxiaodong/new-folder"
}
```

| 字段 | 说明 | target 是否必填 |
|------|------|----------------|
| `mkdir` | 创建目录（含中间目录） | 否 |
| `rename` | 重命名文件/目录 | 是（新路径） |
| `copy` | 复制文件/目录 | 是（目标路径） |
| `move` | 移动文件/目录 | 是（目标路径） |
| `delete` | 删除文件/目录（目录须为空） | 否 |

**响应示例（mkdir）**:
```json
{"ok": true, "action": "mkdir", "path": "/home/zhengxiaodong/new-folder"}
```

---

## 错误码

| 状态码 | 场景 |
|--------|------|
| 403 | 路径在 ALLOWED_ROOTS 之外，或写入受保护文件 |
| 404 | 文件/目录不存在 |
| 413 | 文件超过上传大小限制 |
| 422 | 路径包含符号链接且链接目标在允许范围外 |
