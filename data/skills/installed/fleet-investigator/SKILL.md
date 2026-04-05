---
name: fleet-investigator
description: "面向多服务器对比、远程排障和舰队差异分析的技能。\n  触发场景：fleet、多台、服务器对比、远程、节点、集群"
allowed-tools: server_list server_test_connectivity
metadata:
  version: 0.1.0
  allowed-roles: admin user
  capabilities: fleet-analysis remote-diagnosis
  page-contexts: fleet servers
  owner: shared
---
# Fleet Investigator

适用于多服务器健康对比、某台远程节点异常、舰队容量和差异定位。

执行方式：
1. 明确目标服务器或服务器集合。
2. 优先展示差异和异常节点，不平铺所有原始数据。
3. 如果用户没有给服务器 ID，先帮助识别候选目标。

输出要求：
- 先列异常节点
- 再列差异指标
- 最后列建议操作
