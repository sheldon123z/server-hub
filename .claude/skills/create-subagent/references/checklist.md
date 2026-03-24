# SubAgent Validation Checklist

Run through each item before committing a new or modified SubAgent.

## Required Fields

- [ ] `name` is kebab-case and unique
- [ ] `description` is in English, action-oriented, specific (not "helps with X")
- [ ] `system_prompt` exists and is non-empty
- [ ] `tools` is explicitly specified (not omitted)

## Description Quality

- [ ] Describes WHAT the agent does (action verb)
- [ ] Describes WHEN to delegate to it (trigger conditions)
- [ ] Describes WHAT it returns (output type)
- [ ] Under 200 characters

Good: `"Analyzes Docker container logs to diagnose crashes and restart loops. Returns root cause with fix commands."`
Bad: `"Helps with Docker"`

## System Prompt Structure

- [ ] Starts with role + language: `"你是一个专业的 [角色]，使用中文回复。"`
- [ ] Lists available tools with usage guidance
- [ ] Has numbered workflow steps
- [ ] Specifies output format (what sections to include)
- [ ] Ends with: `"IMPORTANT: Keep your response under 500 words."`
- [ ] Contains `"NEVER read"` for sensitive files if the agent has filesystem access

## Tools

- [ ] Only includes tools the agent actually calls
- [ ] Does NOT include middleware-injected tools (execute, read_file, write_file, edit_file, ls, glob, grep)
- [ ] Uses `_get_tools_by_names([...])` for tools from `tools.py`
- [ ] Uses direct references for tools defined in `subagents.py`
- [ ] Any new `@tool` functions added to `TOOL_REGISTRY`

## Integration

- [ ] Added to `get_subagents()` return list
- [ ] New tools added to `TOOL_RISK_MAP` in `safety.py`
- [ ] `reset_agent_cache()` called or service restarted after changes

## Available Server Tools (from tools.py)

For reference when selecting tools via `_get_tools_by_names()`:

| Tool | Risk | Purpose |
|------|------|---------|
| `get_system_overview` | safe | CPU, memory, GPU, load averages |
| `get_disk_info` | safe | Disk mount points and usage |
| `get_user_resources` | safe | Per-user memory, processes, GPU |
| `get_user_quotas` | safe | Read quota config |
| `update_user_quotas` | moderate | Modify user quotas |
| `list_docker_containers` | safe | List all containers with status |
| `get_container_logs` | safe | Docker container log tail |
| `list_systemd_services` | safe | List managed services |
| `get_service_logs` | safe | Systemd service journal |
| `send_notification` | moderate | Send Telegram message |
| `docker_container_action` | moderate | Start/stop/restart container |
| `docker_compose_action` | moderate | Compose up/down/restart |
| `service_control` | moderate | Start/stop/restart service |
| `execute_ops_script` | danger | Run whitelisted ops script |
| `kill_user_processes` | danger | Kill all user processes |

## SubAgent-Only Tools (from subagents.py)

| Tool | Purpose |
|------|---------|
| `web_search` | Tavily web search |
| `think` | Reflection/assessment pause |
