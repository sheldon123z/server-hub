---
name: security-audit
description: Linux 安全配置审计流程，CIS Benchmark 检查和合规修复建议
---

## 审计工作流
1. 用 get_system_overview 获取系统基本信息
2. 用 check_compliance 执行 CIS Benchmark 检查
3. 分析不合规项的风险等级
4. 生成修复建议

## 重点检查项
- SSH 配置（禁用 root 登录、密钥认证、端口）
- 防火墙规则（ufw/iptables）
- 文件权限（/etc/shadow, /etc/passwd, SUID 文件）
- 用户账户（空密码、超期账户、sudo 权限）
- 系统更新和补丁
- 日志审计配置

## 风险等级
- Critical: 可被远程利用，需立即修复
- High: 本地提权或数据泄露风险
- Medium: 最佳实践偏离，建议修复
- Low: 信息性建议

## 输出格式
### 合规概览
通过/不通过/不适用的统计

### 不合规项
| 项目 | 风险 | 当前值 | 建议值 | 修复命令 |

### 修复优先级
按风险等级排序的修复步骤
