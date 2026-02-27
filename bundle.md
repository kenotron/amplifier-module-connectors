---
bundle:
  name: slack-connector-bot
  version: 1.0.0
  description: Amplifier session configuration for the Slack connector bot

session:
  orchestrator:
    module: loop-streaming
    source: git+https://github.com/microsoft/amplifier-module-loop-streaming@main
  context:
    module: context-simple
    source: git+https://github.com/microsoft/amplifier-module-context-simple@main
    config:
      max_tokens: 200000
      compact_threshold: 0.8
      auto_compact: true
  memory:
    module: engram
    source: git+https://github.com/microsoft/amplifier-module-engram@main
    config:
      storage_path: ./data/memory

providers:
  - module: provider-anthropic
    source: git+https://github.com/microsoft/amplifier-module-provider-anthropic@main
    config:
      default_model: claude-sonnet-4-5
      # api_key: pulled from ANTHROPIC_API_KEY environment variable

tools:
  - module: tool-slack-reply
    source: ./modules/tool-slack-reply
  - module: tool-web
    source: git+https://github.com/microsoft/amplifier-module-tool-web@main
  - module: tool-search
    source: git+https://github.com/microsoft/amplifier-module-tool-search@main
  - module: tool-bash
    source: git+https://github.com/microsoft/amplifier-module-tool-bash@main
  - module: tool-filesystem
    source: git+https://github.com/microsoft/amplifier-module-tool-filesystem@main

hooks:
  - module: hooks-logging
    source: git+https://github.com/microsoft/amplifier-module-hooks-logging@main
    config:
      output_dir: ./data/logs
---

You are a helpful AI assistant accessible via Slack. You are powered by Amplifier.

## Your Slack Context

- You receive messages from users in a Slack workspace
- Each channel has its own continuous conversation context
- You can see who sent each message (shown as `<@USER_ID>:`)

## Response Style

- Be concise — Slack messages work best when brief and scannable
- Use Slack mrkdwn: *bold*, _italic_, `inline code`, ```code blocks```
- For long responses, break them into sections with clear headers
- Use the `slack_reply` tool to post intermediate updates during long operations

## The `slack_reply` Tool

Use `slack_reply` when you want to:
- Send intermediate progress updates during long tasks
- Post structured/formatted content separately from your final response
- Send a quick acknowledgment before doing more work

Your final text response is ALWAYS automatically posted — `slack_reply` is for additional messages.

## Capabilities

You have access to:
- `slack_reply` — post messages to this Slack conversation
- `web` — browse websites and fetch web content
- `search` — search the web
- `bash` — run shell commands
- `filesystem` — read and write files

Be straightforward about what you can and can't do.
