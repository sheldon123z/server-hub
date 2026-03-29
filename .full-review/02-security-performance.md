# Phase 2: Security & Performance Review

## Security Findings (15 items)

### High (6)
| # | 问题 | CWE | 文件 |
|---|------|-----|------|
| S3 | 远程日志路径穿越 (缺尾部斜杠) | CWE-22 | `logs/routes.py:45` |
| S4 | Docker exec 不限制命令 | CWE-78 | `docker/services.py:345` |
| S5 | SSH known_hosts 验证禁用 | CWE-295 | `servers/services.py:264` |
| S6 | 登录端点无速率限制 | CWE-307 | `auth/routes.py:50` |
| S9 | WebTerminal 无资源限制/会话上限 | CWE-269 | `agents/terminal.py:22` |
| S11 | 团队 Agent 工具绕过沙箱保护 | CWE-693 | `agents/teams/safety.py:43` |
| S12 | Hub→Agent 通信使用明文 HTTP | CWE-319 | `servers/agent_client.py:45` |

### Medium (6)
| # | 问题 | CWE |
|---|------|-----|
| S1 | DB 迁移函数 f-string 拼接表名 | CWE-89 |
| S2 | WS 认证 query param token 泄露风险 | CWE-598 |
| S7 | 缺 HTTP 安全头 (CSP/HSTS/X-Frame) | CWE-1021 |
| S8 | Fernet 密钥与 JWT 密钥共用 | CWE-326 |
| S10 | interrupt_on 模式匹配未验证 | CWE-284 |
| S14 | Cookie Secure 依赖可伪造的 X-Forwarded-Proto | CWE-614 |

### Low (3)
| # | 问题 | CWE |
|---|------|-----|
| S13 | DOMPurify artifact 块潜在 XSS | CWE-79 |
| S15 | update_server 动态 SQL 字段名 | CWE-89 |

---

## Performance Findings (13 items)

### Critical (1)
| # | 问题 | 影响 |
|---|------|------|
| P1 | SQLite 全局单连接无并发 | 10+ 用户时延迟 5-20x |

### High (4)
| # | 问题 | 影响 |
|---|------|------|
| P2 | metrics 表 29KB JSON 行 × 90 天 | 50 台服务器 → 180GB |
| P3 | `query_fleet_latest()` 自联结全表扫描 | 50 台时 2-5s |
| P4 | `collect_cpu()` 1s 阻塞线程池 | 线程池耗尽 |
| P5 | 前端 5.9MB JS 包, 主 chunk 1.2MB | 3G 加载 8-15s |

### Medium (6)
| # | 问题 | 影响 |
|---|------|------|
| P6 | DashboardPage 1549 行每 5s 全重渲染 | UI 卡顿 |
| P7 | WS 缓存 50 服务器 85MB | 内存压力 + 连接延迟 |
| P8 | fleet_history 无 server_id 过滤全表扫描 | 84MB JSON 解析 |
| P9 | 默认线程池被所有 run_in_executor 共享 | 线程饥饿 |
| P11 | checkpoint DB 63MB 无清理 | 月级 GB |
| P12 | history 端点 30 天查询 1.2GB JSON | 内存飙升 |

### Low (2)
| # | 问题 |
|---|------|
| P10 | 团队图缓存无淘汰策略 |
| P13 | 清理任务每 60s 无 LIMIT 删除 |

---

## Critical Issues for Phase 3 Context

- **S6**: 无登录速率限制 → 测试应覆盖暴力破解防护
- **S11**: 团队工具绕过沙箱 → 测试需验证安全包装有效性
- **P1**: 单连接瓶颈 → 性能测试需覆盖并发场景
- **P5**: 前端包体积 → 需检查 Vite 构建配置和代码分割
