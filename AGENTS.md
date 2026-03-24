# ServerHub Agent 记忆

此文件是 ServerHub AI 运维助手的长期记忆。Agent 会在对话中通过 edit_file 自动更新此文件。

## 服务器概况

- 主机名: system-NF5468M6
- 系统: Ubuntu 23.04 (Lunar Lobster), Kernel 6.8.0-60-generic
- CPU: Intel Xeon Platinum 8380 @ 2.30GHz, 160 逻辑核心
- 内存: 503GB
- GPU: NVIDIA A800 80GB PCIe
- 存储: / (3.5TB sdb2), /mnt/sda (16.4TB), /mnt/data1-3

## 用户信息

- zhengxiaodong: 管理员，实验室负责人
- wangtao: 学生用户，属于 students 组

## 关键服务

nginx, docker, clash (代理), ollama (本地 LLM), jupyterlab, haproxy, fail2ban, mysql, xrdp, smbd

## Docker 堆栈

- Dify AI 平台: ~/projects/dify/docker (端口 8080/8443)
- LobeChat: /mnt/sda/container_mount/lobe-chat-db (端口 3210)
- Grid AutoPilot: ~/exps/grid-autopilot (多服务: postgres/timescale/redis/neo4j/milvus/kafka)

## 已知问题

- Dify docker-worker-1 频繁重启（待排查）

## 运维经验

（agent 在使用过程中自动学习和更新）

## 用户偏好

（agent 自动记录用户的偏好和习惯）
