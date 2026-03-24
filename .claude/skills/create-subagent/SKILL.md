---
name: create-subagent
description: >
  Create Deep Agents SubAgents for the ServerHub project following the official LangChain specification
  (https://docs.langchain.com/oss/python/deepagents/subagents).
  Use when: (1) adding a new SubAgent to modules/agents/subagents.py, (2) user says "create subagent",
  "add subagent", "new agent", "add a specialized agent", (3) reviewing existing SubAgent definitions
  for spec compliance, (4) user describes a new specialized capability the agent should delegate.
  Enforces required fields (name/description/system_prompt/tools), minimal tool sets, output length
  limits, action-oriented descriptions, and proper TOOL_REGISTRY integration.
---

# Create SubAgent for ServerHub

Build SubAgents for `~/scripts/server-hub/modules/agents/subagents.py` following the
official LangChain Deep Agents specification.

## Required Fields

Every SubAgent dict MUST have exactly these 4 fields:

| Field | Type | Rule |
|-------|------|------|
| `name` | `str` | kebab-case, unique across all subagents |
| `description` | `str` | English, action-oriented, tells main agent WHEN to delegate |
| `system_prompt` | `str` | Chinese response, workflow steps, output format, MUST end with 500-word limit |
| `tools` | `list` | Explicit minimal set. NEVER omit (even though framework inherits if missing) |

Optional: `model` (`str`, format `"provider:model-name"`) to override main agent's model.

## Tool Selection Rules

Deep Agents middleware auto-injects these tools to ALL subagents — do NOT list them:
`execute`, `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`

Only list tools the subagent needs beyond the built-in set:

```python
# Subagent-only tools (defined in subagents.py) — reference directly:
"tools": [web_search, think],

# Server tools (from tools.py) — use helper:
"tools": _get_tools_by_names(["get_container_logs", "get_service_logs"]),

# Combining both:
"tools": [web_search] + _get_tools_by_names(["get_system_overview"]),
```

## Template

```python
{
    "name": "my-agent",
    "description": (
        "Does X by using Y tools. Delegate when Z is needed. "
        "Returns structured analysis with actionable recommendations."
    ),
    "system_prompt": (
        "你是一个专业的 [角色]，使用中文回复。\n\n"
        "可用工具：\n"
        "- tool_a: 用途\n"
        "- tool_b: 用途\n\n"
        "工作流程：\n"
        "1. 步骤一\n"
        "2. 步骤二\n"
        "3. 步骤三\n\n"
        "输出格式：\n"
        "- 摘要（2-3 句）\n"
        "- 详细发现\n"
        "- 建议\n\n"
        "IMPORTANT: Keep your response under 500 words."
    ),
    "tools": _get_tools_by_names(["relevant_tool"]),
},
```

## Integration Steps

After writing the SubAgent dict:

1. Append to `get_subagents()` return list in `subagents.py`
2. If new `@tool` functions created, add to `TOOL_REGISTRY` dict
3. Add new tools to `TOOL_RISK_MAP` in `safety.py` (`SAFE`/`MODERATE`/`DANGER`)
4. Call `reset_agent_cache()` or restart service

## Validation Checklist

See [references/checklist.md](references/checklist.md) for the full pre-commit validation checklist.

## Anti-Patterns

- Omitting `tools` field (inherits 22+ tools — unfocused, violates minimal set)
- No output length limit (causes context bloat in parent agent)
- Vague description like "helps with stuff" (main agent can't decide when to delegate)
- Including `execute`/`read_file`/`grep` in tools (already injected by middleware)
- Forgetting to add new tools to `TOOL_REGISTRY` (breaks admin panel serialization)
