# Simple Agent with Observability

A demonstration of building an AI agent with comprehensive observability using Strands, Braintrust, and OpenTelemetry.

## Overview

This lab showcases a simple AI agent that:
- Uses Strands agent framework
- Provides DuckDuckGo web search capability
- Implements full observability using Braintrust and OpenTelemetry
- Uses either OpenAI or Anthropic models

## Architecture

The agent demonstrates modern AI application patterns:
- **Agent Framework**: Strands for orchestration and tool calling
- **Tools**: DuckDuckGo web search
- **Observability**: Braintrust with OpenTelemetry for tracing
- **Model**: OpenAI or Anthropic via Strands

See [architecture.md](architecture.md) for detailed architecture information about observability and OpenTelemetry.

## Prerequisites

- Python 3.11+
- OpenAI API key or Anthropic API key
- Braintrust API key (FREE, no credit card required - sign up at [https://www.braintrust.dev/](https://www.braintrust.dev/))

## Getting Started

### 1. Get Your API Keys

#### OpenAI API Key
1. Visit [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign up or log in
3. Create a new API key

#### Anthropic API Key
1. Visit [https://console.anthropic.com/](https://console.anthropic.com/)
2. Sign up or log in
3. Navigate to API Keys section
4. Create a new API key

#### Braintrust API Key (FREE)
1. Visit [https://www.braintrust.dev/](https://www.braintrust.dev/)
2. Sign up for a free account (no credit card required)
3. Create a new project (e.g., "My Project" or "simple-agent-observability")
4. Copy your API key from the dashboard
5. **Important**: Note your exact project name (you'll need it for the `.env` file)

### 2. Configure Environment

Copy the example environment file and add your API keys:

```bash
cd simple-agent-observability
cp .env.example .env
```

Edit `.env` and configure your API keys and project:

```bash
OPENAI_API_KEY=your-openai-api-key-here
ANTHROPIC_API_KEY=your-anthropic-api-key-here
BRAINTRUST_API_KEY=your-braintrust-api-key-here
BRAINTRUST_PARENT=project_name:your-project-name-here
MCP_SERVER_URL=https://mcp.context7.com/mcp
```

**Important Configuration Notes:**

1. **Braintrust Parent Format**: Use `BRAINTRUST_PARENT=project_name:YourProjectName`
   - The project name can be anything relevant to your agent
   - Example: `BRAINTRUST_PARENT=project_name:simple-agent-observability`
   - Example: `BRAINTRUST_PARENT=project_name:dsan6725-my-cool-final-project`
   - Backward-compatible alias: `BRAINTRUST_PROJECT`
   - If you set `BRAINTRUST_PROJECT=DSAN6725`, the app will normalize it to `project_name:DSAN6725`

2. **Grouping Multiple Agents**: If you have multiple agents as part of a bigger project, use the same project name for all of them
   - All agents will send traces to the same Braintrust project
   - This creates one top-level grouping for all related agents
   - Example: Three agents for a course project could all use:
     - Agent 1: `BRAINTRUST_PARENT=project_name:dsan6725-final-project`
     - Agent 2: `BRAINTRUST_PARENT=project_name:dsan6725-final-project`
     - Agent 3: `BRAINTRUST_PARENT=project_name:dsan6725-final-project`
   - All traces appear in one "dsan6725-final-project" project in Braintrust

3. **Project Name Matching**: The project name you specify will be auto-created in Braintrust if it doesn't exist, or traces will be sent to an existing project with that name

4. **Model Selection**: The app prefers `OPENAI_API_KEY` when present, otherwise it uses `ANTHROPIC_API_KEY`

5. **MCP Server**: `MCP_SERVER_URL` is optional and defaults to Context7 for the Problem 2 MCP integration

### 3. Install Dependencies

From the repository root, install all dependencies:

```bash
cd /path/to/agents-memory
uv sync
```

### 4. Run the Agent

```bash
cd simple-agent-observability
uv run python agent.py
```

## Usage

Once running, you can ask the agent questions:

```
You: What is the latest news about AI?
Agent: [Searches DuckDuckGo and provides results]

You: Who won the latest Nobel Prize in Physics?
Agent: [Searches DuckDuckGo for current information]

You: What are the current trends in machine learning?
Agent: [Searches web and provides answer based on results]
```

Type `quit` to exit.

## Tools Available

### 1. DuckDuckGo Search
- **Purpose**: Search the web for current information, news, and general topics
- **Usage**: Automatically invoked when the agent needs current web information
- **Examples**:
  - "What's happening in the news today?"
  - "Who is the current president of France?"
  - "What are the latest developments in AI?"

## Observability with Braintrust

Braintrust provides comprehensive observability for your AI agent:

### Viewing Traces

1. Log in to [Braintrust dashboard](https://www.braintrust.dev/)
2. Navigate to your project "simple-agent-observability"
3. View traces showing:
   - Agent invocations
   - Tool calls (DuckDuckGo)
   - LLM requests and responses
   - Timing and latency metrics
   - Token usage
   - Errors and exceptions

**Troubleshooting**: If traces don't appear:
- Verify `BRAINTRUST_PROJECT` uses the correct format: `project_name:YourProjectName`
- Prefer `BRAINTRUST_PARENT`; `BRAINTRUST_PROJECT` is kept as a compatibility alias
- Check that the project name exactly matches your Braintrust project name (case-sensitive)
- Ensure `BRAINTRUST_API_KEY` is valid
- Wait 10-30 seconds for traces to appear after running the agent
- Look for "Failed to export span batch code: 403" errors in the logs (indicates wrong project name)

### What's Being Tracked

Braintrust automatically captures:
- Every agent interaction
- Tool calls with inputs and outputs
- LLM API calls with prompts and completions
- Performance metrics (latency, tokens)
- Error traces and stack traces
- Multi-step agent reasoning

### Benefits of Observability

- **Debugging**: Understand why the agent made specific decisions
- **Performance**: Identify bottlenecks and optimize response times
- **Cost**: Track token usage and API costs
- **Quality**: Monitor response quality and tool usage patterns
- **Production**: Monitor agents in production environments

## Using Alternative Observability Frameworks

While this lab uses Braintrust as an example, the concepts apply to any observability framework. You can replace Braintrust with:

- **Langfuse**: Open-source LLM engineering platform
- **Phoenix**: Open-source observability for LLMs
- **New Relic**: Enterprise APM with OpenTelemetry support
- **Datadog**: Cloud monitoring with AI/LLM tracking
- **Honeycomb**: Observability with OpenTelemetry
- **Custom OpenTelemetry**: Roll your own using OTEL exporters

The key is using OpenTelemetry semantic conventions for GenAI, which provides standardized telemetry across all frameworks.

## Development Workflow

Run all checks before committing:

```bash
uv run ruff check --fix . && uv run ruff format .
```

## Project Structure

```
simple-agent-observability/
├── agent.py              # Main agent script
├── .env.example          # Example environment variables
├── .env                  # Your API keys (not committed)
├── .gitignore           # Git ignore rules
├── README.md            # This file
├── architecture.md      # Architecture and OTEL documentation
├── NOTES.md             # Implementation notes
└── quick-test.sh        # Quick test script

Note: Dependencies are managed in the main repository's pyproject.toml
```

## Learning Objectives

After completing this lab, you will understand:

1. **Agent Frameworks**: How to build agents with Strands
2. **MCP Integration**: How to connect agents to MCP servers
3. **Tool Integration**: How to add custom tools (DuckDuckGo)
4. **Observability**: How to implement comprehensive observability
5. **OpenTelemetry**: How OTEL provides standardized telemetry
6. **GenAI Semantics**: OpenTelemetry semantic conventions for AI

## Troubleshooting

### Agent Not Starting

Check that all environment variables are set:
```bash
cat .env
```

### Braintrust Not Receiving Data

Verify your Braintrust API key and project name:
```bash
echo $BRAINTRUST_API_KEY
echo $BRAINTRUST_PARENT
echo $BRAINTRUST_PROJECT
```

### Tool Calls Failing

Check the logs for detailed error messages. The agent will log all tool invocations and results.

### DuckDuckGo Rate Limiting

If you make too many requests quickly, DuckDuckGo may temporarily rate limit you. Wait a moment and try again.

## Additional Resources

- [Strands Documentation](https://strandsagents.com/)
- [Braintrust Documentation](https://www.braintrust.dev/docs)
- [OpenTelemetry GenAI Semantics](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [DuckDuckGo Search](https://duckduckgo.com/)
- [Anthropic Claude Documentation](https://docs.anthropic.com/)
- [OpenAI Documentation](https://platform.openai.com/docs/overview)

## License

This is a lab assignment for the Applied Generative AI course.
