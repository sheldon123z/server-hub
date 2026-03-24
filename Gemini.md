# Gemini.md - ServerHub Project Guide

This file provides guidance for Gemini CLI when working in the ServerHub repository.

## Project Overview
ServerHub is a FastAPI-based Linux server management system with integrated AI operations agents. It provides monitoring, Docker/service management, user resource control, and automated AI patrolling.

**Tech Stack**: FastAPI, Jinja2, HTMX, Alpine.js, SQLite (aiosqlite), Deep Agents (LangGraph), xterm.js.

## Environment & Commands
- **Environment**: Use `serverhub` conda environment (Python 3.11).
- **Run Development**: `python main.py` or `uvicorn main:app --host 0.0.0.0 --port 9900 --reload --workers 1`
- **Constraint**: **Workers MUST be 1** for SQLite consistency and agent state.
- **Lint/Format**: Use standard Python tools (`ruff`, `black`) if available in the environment.

## Architecture Highlights
- **Module System**: `modules/*/` are auto-discovered via `MODULE_INFO` and `router` in `__init__.py`.
- **AI Agents**: Located in `modules/agents/`, built on the **Deep Agents** framework.
  - **Backend**: `SafeLocalShellBackend` for sandboxed execution (strips secrets, ulimit restrictions).
  - **Memory**: 
    - Short-term: `data/agent-checkpoints.db`
    - Long-term: `data/agent-memory.md` (Updated via `edit_file`)
    - Structured: `data/agent-store.db`
- **Databases**: Three SQLite files in `data/`: `server-hub.db`, `agent-checkpoints.db`, `agent-store.db`.

## Development Principles
- **Framework First**: Always leverage the **Deep Agents** framework's existing mechanisms before custom implementations.
- **Surgical Edits**: Use `replace` for targeted code changes. Maintain existing patterns and naming conventions.
- **Safety**: Never read or log sensitive files (`.env`, `~/.api_keys`, etc.).
- **Validation**: 
  - Verify changes by running the app or specific test scripts if available.
  - Check Python 3.11 compatibility (e.g., f-string backslash constraints).
- **Audit**: All destructive API actions (`POST/PUT/DELETE` to `/api/*`) are logged via `audit_middleware.py`.

## Git Workflow
- **No Auto-Commit**: Never commit unless explicitly asked.
- **Commit Messages**: Clear, concise, and "why"-focused.
