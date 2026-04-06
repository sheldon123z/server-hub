"""Pipeline 内置模板 — 4 种常用运维流水线 YAML 定义"""

import logging

logger = logging.getLogger(__name__)

SERVER_INIT_TEMPLATE = """\
name: server-init
display_name: 服务器初始化流水线
description: 新机器上架全流程 — 连通性检查、系统配置、服务安装、AI 验证、审批、通知
version: 1
max_concurrent_runs: 1
timeout: 3600

trigger:
  type: manual

params:
  - name: target_server
    type: string
    required: true
    description: 目标服务器 ID 或 IP
  - name: deploy_services
    type: array
    default: ["nginx", "docker"]
    description: 需要安装的服务列表
  - name: ssh_username
    type: string
    default: root
    description: SSH 用户名

steps:
  - id: check-connectivity
    type: ssh
    name: 连通性检查
    host: "{{params.target_server}}"
    username: "{{params.ssh_username}}"
    command: "echo ok && uname -a"
    timeout: 30
    on_failure: abort

  - id: system-setup
    type: playbook
    name: 系统基础配置
    playbook_id: "system-init-template"
    params:
      server_id: "{{params.target_server}}"

  - id: install-services
    type: parallel
    name: 并行安装服务
    branches:
      - id: install-docker
        type: shell
        name: 安装 Docker
        command: "curl -fsSL https://get.docker.com | sh"
      - id: install-nginx
        type: shell
        name: 安装 Nginx
        command: "apt-get install -y nginx"

  - id: ai-verify
    type: agent
    name: AI 健康验证
    prompt: "检查服务器 {{params.target_server}} 的服务状态，确认 Docker 和 Nginx 已正确安装并运行。返回 JSON 包含 confidence (0-1) 和 issues 数组。"
    model: fast
    output_format: json

  - id: decide-action
    type: condition
    name: 判断是否需要人工审批
    expression: "{{steps.ai-verify.output.confidence}} >= 0.9"
    on_true: notify-done
    on_false: admin-approve

  - id: admin-approve
    type: approval
    name: 管理员确认上线
    assignee: admin
    timeout: 3600
    on_timeout: abort

  - id: notify-done
    type: notify
    name: 完成通知
    channel: telegram
    message: "服务器 {{params.target_server}} 初始化完成"
"""

AUTO_HEAL_TEMPLATE = """\
name: auto-heal
display_name: 故障自愈流水线
description: 告警触发后自动诊断、审批修复、验证恢复
version: 1
max_concurrent_runs: 3
timeout: 1800

trigger:
  type: alert

params:
  - name: alert_context
    type: object
    description: 告警上下文信息（由系统注入）

steps:
  - id: diagnose
    type: agent
    name: AI 诊断根因
    prompt: "分析以下告警信息，诊断根本原因并推荐修复方案。告警上下文: {{params.alert_context}}。返回 JSON 包含 root_cause, severity (low/medium/high/critical), recommended_playbook, confidence 字段。"
    model: fast
    output_format: json
    on_failure: abort

  - id: approve-fix
    type: approval
    name: 确认修复方案
    assignee: admin
    timeout: 1800
    on_timeout: abort

  - id: fix
    type: playbook
    name: 执行修复
    playbook_id: "{{steps.diagnose.output.recommended_playbook}}"
    params:
      alert_context: "{{params.alert_context}}"
    on_failure: notify_continue

  - id: wait-recovery
    type: delay
    name: 等待服务恢复
    seconds: 30

  - id: verify
    type: agent
    name: AI 验证恢复
    prompt: "验证告警相关服务是否已恢复正常。原始告警: {{params.alert_context}}。返回 JSON 包含 recovered (bool), details, confidence 字段。"
    model: fast
    output_format: json

  - id: check-ok
    type: condition
    name: 是否恢复正常
    expression: "{{steps.verify.output.recovered}} == True"
    on_true: notify-success
    on_false: notify-failure

  - id: notify-success
    type: notify
    name: 恢复成功通知
    channel: telegram
    message: "故障已自愈: {{steps.diagnose.output.root_cause}}"

  - id: notify-failure
    type: notify
    name: 恢复失败通知
    channel: telegram
    message: "故障自愈失败，需人工介入。根因: {{steps.diagnose.output.root_cause}}"
"""

DAILY_PATROL_TEMPLATE = """\
name: daily-patrol
display_name: 日常巡检流水线
description: 每日定时并行检查资源、安全、日志，AI 汇总后条件分支通知
version: 1
max_concurrent_runs: 1
timeout: 1800

trigger:
  type: cron
  cron: "0 8 * * *"

params: []

steps:
  - id: checks
    type: parallel
    name: 并行巡检
    branches:
      - id: resource-check
        type: shell
        name: 资源检查
        command: "echo '=== CPU ===' && top -bn1 | head -5 && echo '=== Memory ===' && free -h && echo '=== Disk ===' && df -h"
      - id: security-scan
        type: shell
        name: 安全扫描
        command: "echo '=== Failed SSH ===' && journalctl -u sshd --since '24 hours ago' | grep -c 'Failed' || echo 0 && echo '=== Listening Ports ===' && ss -tlnp"
      - id: log-analysis
        type: agent
        name: 日志分析
        prompt: "分析过去 24 小时的系统日志，识别异常模式。重点关注 OOM、服务重启、磁盘错误。返回 JSON 包含 issues 数组和 summary 字段。"
        model: fast
        output_format: json

  - id: summarize
    type: agent
    name: AI 汇总报告
    prompt: "基于以下巡检结果生成综合报告。资源: {{steps.resource-check.output}}。安全: {{steps.security-scan.output}}。日志: {{steps.log-analysis.output}}。返回 JSON 包含 overall_status (ok/warning/critical), summary, recommendations 字段。"
    model: fast
    output_format: json

  - id: has-issue
    type: condition
    name: 是否有异常
    expression: "{{steps.summarize.output.overall_status}} != ok"
    on_true: notify-warning
    on_false: notify-ok

  - id: notify-warning
    type: notify
    name: 异常告警
    channel: telegram
    message: "日常巡检发现异常: {{steps.summarize.output.summary}}"

  - id: notify-ok
    type: notify
    name: 正常通知
    channel: telegram
    message: "日常巡检正常，无异常发现"
"""

SECURITY_SCAN_TEMPLATE = """\
name: security-scan
display_name: 安全扫描流水线
description: 合规检查、端口扫描、SSH 审计、AI 分析、条件审批修复
version: 1
max_concurrent_runs: 1
timeout: 3600

trigger:
  type: manual

params:
  - name: target_server
    type: string
    required: false
    description: 目标服务器（留空则扫描本机）

steps:
  - id: compliance
    type: playbook
    name: 合规基线检查
    playbook_id: "security-compliance"
    params:
      server_id: "{{params.target_server}}"
    on_failure: skip

  - id: port-scan
    type: shell
    name: 端口扫描
    command: "ss -tlnp | grep LISTEN"
    on_failure: skip

  - id: ssh-audit
    type: shell
    name: SSH 配置审计
    command: "echo '=== SSH Config ===' && grep -E '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|MaxAuthTries|Protocol)' /etc/ssh/sshd_config 2>/dev/null || echo 'SSH config not found' && echo '=== Failed Logins (24h) ===' && journalctl -u sshd --since '24 hours ago' 2>/dev/null | grep -c 'Failed' || echo 0"
    on_failure: skip

  - id: ai-report
    type: agent
    name: AI 安全报告
    prompt: "基于以下安全扫描结果生成安全报告。合规: {{steps.compliance.output}}。端口: {{steps.port-scan.output}}。SSH: {{steps.ssh-audit.output}}。返回 JSON 包含 severity (low/medium/high/critical), findings 数组, recommendations 数组。"
    model: fast
    output_format: json

  - id: severity-check
    type: condition
    name: 严重性判断
    expression: "{{steps.ai-report.output.severity}} == critical"
    on_true: approve-fix
    on_false: notify-result

  - id: approve-fix
    type: approval
    name: 高风险修复审批
    assignee: admin
    timeout: 7200
    on_timeout: abort

  - id: auto-fix
    type: agent
    name: 自动修复
    prompt: "根据安全报告中的建议，生成并执行修复命令。发现: {{steps.ai-report.output.findings}}。建议: {{steps.ai-report.output.recommendations}}。仅修复 critical 和 high 级别问题。"
    model: fast
    on_failure: notify_continue

  - id: notify-result
    type: notify
    name: 扫描结果通知
    channel: telegram
    message: "安全扫描完成 — 严重性: {{steps.ai-report.output.severity}}，发现 {{steps.ai-report.output.findings}} 个问题"
"""


def get_builtin_templates() -> list[dict]:
    """返回所有内置模板列表"""
    return [
        {
            "id": "server-init",
            "display_name": "服务器初始化",
            "description": "新机器上架全流程 — 连通性检查、系统配置、服务安装、AI 验证、审批、通知",
            "category": "部署",
            "yaml_content": SERVER_INIT_TEMPLATE,
        },
        {
            "id": "auto-heal",
            "display_name": "故障自愈",
            "description": "告警触发后自动诊断、审批修复、验证恢复",
            "category": "运维",
            "yaml_content": AUTO_HEAL_TEMPLATE,
        },
        {
            "id": "daily-patrol",
            "display_name": "日常巡检",
            "description": "每日定时并行检查资源、安全、日志，AI 汇总后条件分支通知",
            "category": "监控",
            "yaml_content": DAILY_PATROL_TEMPLATE,
        },
        {
            "id": "security-scan",
            "display_name": "安全扫描",
            "description": "合规检查、端口扫描、SSH 审计、AI 分析、条件审批修复",
            "category": "安全",
            "yaml_content": SECURITY_SCAN_TEMPLATE,
        },
    ]
