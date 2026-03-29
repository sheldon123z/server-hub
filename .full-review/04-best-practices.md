# Phase 4: Best Practices & Standards

## Framework & Language Findings (12 items)

### High (3)
| # | 问题 | 影响范围 |
|---|------|---------|
| F1 | `asyncio.get_event_loop().run_in_executor` 废弃 (28 处) | 8 个文件 |
| F2 | 手动 Settings 类而非 pydantic-settings | config.py |
| F3 | Vite 无 manualChunks，3.7MB 单体 JS | 前端构建 |

### Medium (5)
| # | 问题 |
|---|------|
| F4 | `typing.Optional` 而非 `X \| None` (7 文件) |
| F5 | 无 Pydantic `model_config` / `ConfigDict` |
| F6 | 80+ 端点无 `response_model` |
| F9 | TypeScript `any` 24 处 |
| F12 | ErrorBoundary 仅包裹 1/18 页面 |

### Low (4)
| # | 问题 |
|---|------|
| F7 | 废弃依赖 Jinja2 仍在 requirements.txt |
| F8 | autoprefixer/postcss 废弃 (Tailwind v4 不需要) |
| F10 | 未使用 TS `satisfies` 操作符 |
| F11 | 未使用 Python `match/case` |

---

## CI/CD & DevOps Findings (12 items)

### Critical (2)
| # | 问题 | 风险 |
|---|------|------|
| O1 | 无 CI/CD 流水线 | 无自动测试/构建门禁 |
| O2 | .env 含明文密钥 + 弱密码 admin123 | 密钥泄露 |

### High (3)
| # | 问题 |
|---|------|
| O3 | systemd 单元缺安全加固指令 |
| O5 | 无 SQLite 数据库备份策略 |
| O6 | 无登录速率限制 (确认 S6) |

### Medium (5)
| # | 问题 |
|---|------|
| O4 | 无结构化日志配置 |
| O7 | 无 HTTP 安全头 (确认 S7) |
| O8 | 无 workers=1 运行时断言 |
| O9 | Python 依赖仅最低版本约束 |
| O10 | 无错误追踪 (Sentry 等) |

### Low (2)
| # | 问题 |
|---|------|
| O11 | SQLite 缺 busy_timeout PRAGMA |
| O12 | 无 dev/prod 配置分离 |
