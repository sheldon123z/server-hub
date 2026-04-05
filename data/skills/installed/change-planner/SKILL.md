---
name: change-planner
description: 面向服务重启、配置变更和维护窗口的变更规划技能。
allowed-tools: service_control docker_container_action playbook_create
metadata:
  version: 0.1.0
  allowed-roles: admin
  capabilities: change-planning risk-assessment
  page-contexts: services docker cron
  owner: shared
---
# Change Planner

适用于服务重启、配置切换、镜像升级和有风险的运维变更。

执行方式：
1. 先说明影响面和潜在中断。
2. 主动拆出检查前置、执行步骤、回滚方案。
3. 涉及危险操作时引导审批，不直接跳过。

输出要求：
- 变更目标
- 风险与影响
- 执行步骤
- 回滚方案
