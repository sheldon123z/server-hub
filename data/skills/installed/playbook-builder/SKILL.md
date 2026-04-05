---
name: playbook-builder
description: 将高频运维对话沉淀为可复用剧本或 skill 草稿的技能。
allowed-tools: playbook_create playbook_list playbook_search
metadata:
  version: 0.1.0
  allowed-roles: admin
  capabilities: playbook-authoring automation
  page-contexts: agents playbooks
  owner: shared
---
# Playbook Builder

适用于重复性的运维操作、人工巡检流程和需要标准化的排障路径。

执行方式：
1. 识别对话中可复用的步骤序列。
2. 判断更适合沉淀成 playbook 还是保持为提示型 skill。
3. 给出参数化建议，避免把环境常量硬编码进模板。

输出要求：
- 可复用目标
- 建议的剧本参数
- 推荐保存方式
