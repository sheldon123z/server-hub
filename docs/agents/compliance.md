# 合规基线检查

合规基线检查基于 CIS（Center for Internet Security）Benchmark 标准，通过 `data/compliance_baselines.json` 配置文件驱动，提供自动检查和可选的自动修复能力。

---

## 15 条 CIS 基线

### SSH 安全（4 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| ssh_root_login | 禁止 root 远程登录 | high | 否 |
| ssh_empty_password | 禁止空密码登录 | critical | 是 |
| ssh_max_auth_tries | SSH 最大认证尝试次数 ≤ 4 | medium | 是 |
| ssh_protocol_2 | 仅使用 SSH Protocol 2 | high | 否 |

### 口令策略（3 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| password_max_days | 密码最大有效期 ≤ 90 天 | medium | 否 |
| password_min_days | 密码最小修改间隔 ≥ 1 天 | low | 否 |
| password_min_length | 密码最小长度 ≥ 8 字符 | medium | 否 |

### 权限控制（1 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| sudo_requiretty | 检查 sudo 配置安全性（NOPASSWD 滥用）| medium | 否 |

### 文件权限（1 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| world_writable_files | 关键目录无全局可写文件 | medium | 否 |

### 网络安全（2 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| firewall_active | 防火墙已启用 | high | 否 |
| fail2ban_running | Fail2ban 防暴力破解已运行 | high | 否 |

### 内核安全（2 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| kernel_randomize_va | ASLR 地址随机化已启用 | high | 否 |
| core_dump_restricted | Core dump 已限制 | low | 否 |

### 审计日志（1 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| syslog_running | 系统日志服务已运行 | high | 否 |

### 文件系统（1 条）

| ID | 名称 | 严重级别 | 可自动修复 |
|----|------|---------|-----------|
| tmp_noexec | /tmp 挂载限制（建议）| low | 否 |

---

## 严重级别说明

| 级别 | 含义 |
|------|------|
| critical | 严重安全漏洞，必须立即修复 |
| high | 高风险，应尽快修复 |
| medium | 中等风险，建议修复 |
| low | 低风险或建议项，可选修复 |

---

## check_compliance 工具使用

```python
# 检查全部基线
check_compliance()

# 只检查 SSH 安全类
check_compliance(category="SSH安全")

# 可用分类
# SSH安全 / 口令策略 / 权限控制 / 文件权限 / 网络安全 / 内核安全 / 审计日志 / 文件系统
```

### 检查逻辑

每条基线包含以下字段：

| 字段 | 说明 |
|------|------|
| `check_cmd` | 检查命令（Shell），10 秒超时 |
| `expect_contains` | 输出必须包含此字符串 |
| `fail_if_contains` | 输出包含此字符串则判定失败 |
| `expect_regex` | 输出必须匹配此正则表达式 |
| `expect_max` | 与 `expect_regex` 配合，提取数值必须 ≤ 此值 |
| `expect_min` | 与 `expect_regex` 配合，提取数值必须 ≥ 此值 |
| `fix_guide` | 手动修复指导（PASS 时不显示）|

### 返回格式

```
## 安全合规检查报告

合规率: **86.7%** (13/15 通过)

| 检查项 | 结果 | 严重级别 | 详情 |
|---|---|---|---|
| 禁止 root 远程登录 | PASS | high | no |
| 禁止空密码登录 | FAIL | critical | 检测到不安全配置 → 设置 PermitEmptyPasswords no |
| ...
```

---

## auto_fix_compliance 自动修复流程

仅对 `auto_fixable: true` 的基线项有效（当前有 2 条）：

1. **ssh_empty_password**：执行 `sed` 修改 sshd_config + `systemctl reload sshd`
2. **ssh_max_auth_tries**：执行 `sed` 修改 MaxAuthTries + `systemctl reload sshd`

### 修复流程

```python
auto_fix_compliance(item_id="ssh_empty_password")

# 内部步骤：
# 1. 查找基线项，验证 auto_fixable == true
# 2. 执行 check_cmd 记录修复前状态
# 3. 执行 fix_cmd（30 秒超时）
# 4. 再次执行 check_cmd 验证修复结果
# 5. 返回修复前/后对比报告
```

### 返回示例

```markdown
## 合规修复: 禁止空密码登录

**状态**: 已修复
**修复前**: PermitEmptyPasswords yes
**修复后**: PermitEmptyPasswords no
**命令输出**: (无输出)
```

### 风险提示

`auto_fix_compliance` 被标记为 `danger` 级别，在 `supervised` 模式下始终触发人工审批，确保运维人员确认后再执行修复。

---

## 合规基线配置文件格式

`data/compliance_baselines.json` 是一个 JSON 数组，每个对象的结构：

```json
{
  "id": "ssh_empty_password",
  "category": "SSH安全",
  "name": "禁止空密码登录",
  "severity": "critical",
  "check_cmd": "grep -E '^\\s*PermitEmptyPasswords' /etc/ssh/sshd_config",
  "expect_contains": "no",
  "fail_if_contains": "yes",
  "auto_fixable": true,
  "fix_cmd": "sudo sed -i 's/.../PermitEmptyPasswords no/' /etc/ssh/sshd_config && sudo systemctl reload sshd",
  "fix_guide": "设置 PermitEmptyPasswords no"
}
```

添加新基线只需在此文件中追加记录，无需修改 Python 代码。

---

## 合规巡检任务

内置巡检任务 `security_compliance` 每天运行一次，自动执行全量合规检查：

- **间隔**：1440 分钟（每天一次）
- **工具**：`check_compliance`
- **Prompt**：对不合规项按严重程度分类，重点关注 high 和 critical 级别

也可单独创建分类巡检（如仅检查 SSH 安全）。
