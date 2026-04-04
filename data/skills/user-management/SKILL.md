---
name: user-management
description: Linux 用户管理和资源配额控制工作流
---

## 用户管理操作
- manage_linux_user: 创建/删除/修改用户
- get_user_resources: 查看用户资源使用
- get_user_login_history_tool: 登录历史
- get_active_sessions_tool: 活跃会话
- kill_single_process_tool: 终止进程
- check_quota_violations: 配额违规检查

## 资源配额规范
- students 组默认: 80GB 内存 / 600 进程 / 6 CPU 核心
- 新用户务必加入 students 组: sudo usermod -aG students <username>
- 管理员用户（zhengxiaodong, root）不受配额限制

## 常见场景
- 用户挂机占用资源 → check_quota_violations → 通知/kill
- 新建学生用户 → manage_linux_user create + 加入 students 组
- GPU 占用排查 → get_user_resources 查看 GPU 进程
