## Agentic Coding Hooks

**Definition:** Hooks are deterministic handlers executed at defined points in an agent’s lifecycle. They receive structured event context and may observe, validate, block, modify, or extend agent behavior.

**Common format:**

1. Lifecycle event occurs.
2. Optional matcher filters the event.
3. Agent supplies structured JSON context.
4. A script, command, prompt, MCP tool, HTTP endpoint, or subagent runs.
5. The handler allows, blocks, modifies, retries, or records the action.

**Common events:**

- Session start/end
- User prompt submitted
- Before/after tool use
- Before/after file changes
- Before/after model calls
- Permission request
- Context compaction
- Subagent start/stop
- Agent completion/interruption

**Provider references:**

- Google Antigravity: https://antigravity.google/docs/hooks/
- Anthropic Claude Code: https://code.claude.com/docs/en/hooks
- OpenAI Codex: https://learn.chatgpt.com/docs/hooks
- Google Gemini CLI: https://geminicli.com/docs/hooks/
- GitHub Copilot: https://docs.github.com/en/copilot/reference/hooks-reference
- Cursor: https://cursor.com/docs/hooks
- Amazon Kiro: https://kiro.dev/docs/ide/whats-new-v1/hooks/
- Windsurf/Devin Cascade: https://docs.devin.ai/desktop/cascade/hooks

**Standardization status:** The providers share the general event → matcher → context → handler → outcome model, but hook names, schemas, configuration locations, and control semantics remain provider-specific.