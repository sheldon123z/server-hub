---
name: docker-ops
description: Docker 容器和 Compose 堆栈运维工作流，包括日志分析、资源清理和故障排查
---

## 常用操作
- list_docker_containers: 查看运行中容器
- get_container_logs: 查看容器日志（支持 tail/since 参数）
- docker_container_action: 启动/停止/重启容器
- docker_compose_action: 管理 Compose 堆栈
- docker_container_exec: 在容器内执行命令
- docker_prune: 清理未用资源

## 关键堆栈
- Dify AI 平台: ~/projects/dify/docker（注意: worker 容器可能频繁重启）
- Grid AutoPilot: ~/exps/grid-autopilot/
- LobeChat: /mnt/sda/container_mount/lobe-chat-db

## 故障排查流程
1. docker_container_action status 查看容器状态
2. get_container_logs 查看最近日志
3. 分析错误模式（OOM、连接拒绝、配置错误）
4. docker_container_exec 进入容器检查

## 资源清理
docker_prune 前先确认无重要的停止容器
