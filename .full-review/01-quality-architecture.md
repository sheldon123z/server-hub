# Phase 1: Code Quality & Architecture Review

## Code Quality Findings (21 items)

### Critical (2)
| # | 问题 | 文件 | 说明 |
|---|------|------|------|
| Q1 | `get_user_quota()` 调用签名错误 | `users/services.py:615` | 定义 3 参数，调用时只传 2 个 → 运行时 TypeError |
| Q2 | `_table_columns` SQL 注入向量 | `database.py:17` | f-string 拼接表名，PRAGMA 不支持参数化 |

### High (6)
| # | 问题 | 影响范围 |
|---|------|---------|
| Q3 | `except Exception: pass` 吞异常 | 20+ 处，心跳/配额/代理关键路径 |
| Q4 | f-string 日志 (`logger.warning(f"...")`) | 83 处跨 22 文件 |
| Q5 | 废弃的 `asyncio.get_event_loop().run_in_executor` | 20+ 处 |
| Q6 | 远程 dispatch 代码重复 (`if server_id != "local"`) | 27 处跨 7 个模块 |
| Q7 | DashboardPage.tsx 1549 行 God Component | 前端 |
| Q8 | chat.py event_generator() 228 行 / 7 层嵌套 | agents/routes/chat.py |

### Medium (9)
| # | 问题 |
|---|------|
| Q9 | 函数内 inline import 标准库 (json, datetime) |
| Q10 | `__import__("datetime")` hack |
| Q11 | TypeScript `any` 24 处 |
| Q12 | API 响应格式不一致 (local vs remote) |
| Q13 | database.py init_tables() 490 行单体 SQL |
| Q14 | config.py 硬编码绝对路径 |
| Q15 | 前端类型定义散落在页面文件而非 types/ |
| Q16 | useSSEChat.ts 23 处 `as string` 强转 |
| Q17 | Agent 缓存 key 不含 model ID |

### Low (4)
| # | 问题 |
|---|------|
| Q18 | import 排序不一致 |
| Q19 | `list_containers(all=True)` 遮蔽内置 `all` |
| Q20 | 全局可变 DB 单例不利于测试 |
| Q21 | Settings 类手动读 env 而非 pydantic-settings |

---

## Architecture Findings (20 items)

### Critical (1)
| # | 问题 | 说明 |
|---|------|------|
| A1 | Teams 模块 15 个端点 **零前端覆盖** | 完整后端但无 React 页面 |

### High (3)
| # | 问题 |
|---|------|
| A2 | monitoring/routes.py 446 行含 WSManager + 业务逻辑 (违反 routes 只做 HTTP 层) |
| A3 | SQLite 单连接全局状态，无 workers=1 断言 |
| A4 | agents 模块已成内部单体 (11 路由子模块 + teams + patrol + RAG + skills) |

### Medium (12)
| # | 问题 |
|---|------|
| A5 | Dashboard 模块仅 1 端点，与 monitoring/realtime 功能重复 |
| A6 | API 响应信封不统一 (`"ok"` vs `"success"`) |
| A7 | audit/routes.py 含废弃的 Jinja2 辅助函数 |
| A8 | scheduler → users 跨模块 import 隐式耦合 |
| A9 | schema 迁移系统脆弱 (无版本号/回滚) |
| A10 | 多表缺 FOREIGN KEY 约束 |
| A11 | Teams engine.py 重复 LLM 解析逻辑 |
| A12 | WS 认证允许 query param token (日志泄露风险) |
| A13 | 部分模块缺 Pydantic 请求模型 (alerts, patrols 用 raw dict) |
| A14 | server_id 支持不一致 (assets/notifications/audit 静默忽略) |
| A15 | teams/routes.py 直接执行 SQL 查询 |
| A16 | SPA catch-all 吞掉无效 API 路径的 404 |

### Low (4)
| # | 问题 |
|---|------|
| A17 | proxy 模块 7 个遗留端点仍注册 |
| A18 | TeamStore 每次请求新建实例 |
| A19 | 5/17 模块不遵循 routes.py + services.py 模式 |
| A20 | `asyncio.get_event_loop()` 应改 `get_running_loop()` |

---

## Frontend-Backend Coverage Gap

### 完全未覆盖的后端功能 (需前端建设)
1. **智能体团队** `/api/agents/teams/*` — 15 个端点，0 前端调用 (**Critical**)
2. **Inode 监控** `/api/monitoring/inode` — 数据采集但未展示
3. **防火墙规则** `/api/network/firewall` — 无 UI
4. **RAG 管理** `/api/agents/admin/rag` + reindex — 无管理入口
5. **异步任务** `/api/agents/async-tasks` — 列表/详情/删除无 UI
6. **Cron 备份列表** `/api/cron/backups`
7. **Agent 事件日志** `/api/agents/events`

---

## Critical Issues for Phase 2 Context

- **Q2**: SQL 注入在 database.py — 安全审计需重点检查
- **A12**: WebSocket query param token — 安全审计需评估
- **Q6**: 远程 dispatch 重复代码 — 性能审计需检查错误处理一致性
- **A3**: SQLite 单连接 — 性能瓶颈评估
