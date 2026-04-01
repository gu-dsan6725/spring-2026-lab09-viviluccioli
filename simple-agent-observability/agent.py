"""
Simple Strands Agent with DuckDuckGo and Braintrust Observability.

This agent demonstrates:
- DuckDuckGo web search tool
- Braintrust observability using OpenTelemetry
- OpenAI or Anthropic models via Strands
"""

import asyncio
import json
import logging
import os
from typing import Optional

from braintrust.otel import BraintrustSpanProcessor
from ddgs import DDGS
from dotenv import load_dotenv
from mcp.client.streamable_http import streamablehttp_client
from opentelemetry.sdk.trace import TracerProvider
from strands import Agent
from strands.telemetry import StrandsTelemetry
from strands.tools.decorator import tool
from strands.tools.mcp import MCPClient


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()


def _get_env_var(
    key: str,
    default: Optional[str] = None
) -> str:
    """Get environment variable or raise error if not found."""
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Environment variable {key} not set")
    return value


@tool
def duckduckgo_search(
    query: str,
    max_results: int = 5
) -> str:
    """
    Search DuckDuckGo for the given query. Use this for current events, news, general information, or any topic that requires web search.

    Args:
        query: The search query string
        max_results: Maximum number of results to return

    Returns:
        JSON string containing search results
    """
    try:
        logger.info(f"Searching DuckDuckGo for: {query}")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        logger.info(f"Found {len(results)} results")
        return json.dumps(results, indent=2)

    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return json.dumps({"error": str(e)})


def _setup_observability() -> TracerProvider:
    """
    Set up OpenTelemetry with Braintrust for observability.

    Returns:
        Configured TracerProvider instance
    """
    logger.info("Setting up Braintrust observability")

    # Get Braintrust configuration
    braintrust_api_key = _get_env_var("BRAINTRUST_API_KEY")
    braintrust_parent = os.getenv("BRAINTRUST_PARENT")
    braintrust_project = os.getenv("BRAINTRUST_PROJECT")

    if braintrust_parent:
        normalized_parent = braintrust_parent
    elif braintrust_project:
        normalized_parent = (
            braintrust_project
            if ":" in braintrust_project
            else f"project_name:{braintrust_project}"
        )
        if normalized_parent != braintrust_project:
            logger.warning(
                "BRAINTRUST_PROJECT=%s does not include a parent prefix; "
                "using %s for Braintrust export",
                braintrust_project,
                normalized_parent,
            )
    else:
        raise ValueError(
            "Set BRAINTRUST_PARENT (preferred) or BRAINTRUST_PROJECT in your .env file"
        )

    # Create TracerProvider and add Braintrust processor
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(
        BraintrustSpanProcessor(
            api_key=braintrust_api_key,
            parent=normalized_parent
        )
    )

    # Set tracer provider as global
    from opentelemetry import trace
    trace.set_tracer_provider(tracer_provider)

    logger.info("Braintrust observability configured for parent: %s", normalized_parent)
    return tracer_provider


def _create_model():
    """Create a Strands model from available provider credentials."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key

        from strands.models import OpenAIModel

        logger.info("Using OpenAI model backend")
        return OpenAIModel(model_id="gpt-4o-mini")

    if anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key

        from strands.models import AnthropicModel

        logger.info("Using Anthropic model backend")
        return AnthropicModel(
            model_id="claude-3-haiku-20240307",
            max_tokens=4096
        )

    raise ValueError(
        "No model API key found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in your .env file."
    )


def _create_streamable_http_transport():
    """Create a streamable HTTP transport for the configured MCP server."""
    mcp_server_url = os.getenv("MCP_SERVER_URL", "https://mcp.context7.com/mcp")
    return streamablehttp_client(mcp_server_url)


def _setup_mcp_client() -> tuple[MCPClient, list]:
    """Connect to the MCP server and load its tools."""
    mcp_server_url = os.getenv("MCP_SERVER_URL", "https://mcp.context7.com/mcp")
    logger.info("Connecting to MCP server: %s", mcp_server_url)

    mcp_client = MCPClient(
        _create_streamable_http_transport,
        prefix="context7",
    )
    mcp_client.start()

    try:
        mcp_tools = list(mcp_client.list_tools_sync())
    except Exception:
        mcp_client.stop(None, None, None)
        raise

    logger.info("Loaded %d MCP tools from %s", len(mcp_tools), mcp_server_url)
    for tool_obj in mcp_tools:
        logger.info("MCP tool available: %s", tool_obj.tool_name)

    return mcp_client, mcp_tools


def _create_agent() -> tuple[Agent, MCPClient]:
    """
    Create and configure the Strands agent.

    Returns:
        Configured Agent instance and active MCP client
    """
    logger.info("Creating Strands agent")

    # Set up observability
    tracer_provider = _setup_observability()
    telemetry = StrandsTelemetry(tracer_provider=tracer_provider)

    # Configure the agent with system prompt
    system_prompt = """You are a helpful AI assistant with access to DuckDuckGo web search and Context7 MCP tools.

Use DuckDuckGo for current events, recent news, and general web information.
Use the Context7 MCP tools for programming and framework documentation when relevant.
If the user asks about available MCP tools, explain that Context7 tools were loaded at startup and name the tools you can access when possible.
Provide clear, accurate, and helpful responses based on the search results or MCP tool output.
Always cite your sources when using search results."""

    model = _create_model()
    mcp_client, mcp_tools = _setup_mcp_client()

    # Create agent - observability is already configured globally via TracerProvider
    agent = Agent(
        system_prompt=system_prompt,
        model=model,
        tools=[duckduckgo_search] + mcp_tools
    )

    logger.info("Agent created successfully with Braintrust observability")
    return agent, mcp_client


async def _run_agent_async(
    agent: Agent,
    user_input: str
) -> str:
    """
    Run the agent asynchronously with the given input.

    Args:
        agent: The Strands agent instance
        user_input: User's question or prompt

    Returns:
        Agent's response
    """
    logger.info(f"Processing user input: {user_input}")

    response = await agent.invoke_async(user_input)

    logger.info("Agent response generated")
    return response


def main() -> None:
    """Main function to run the agent."""
    logger.info("Starting Simple Agent with Observability")
    mcp_client: MCPClient | None = None

    try:
        # Create agent
        agent, mcp_client = _create_agent()

        print("\n" + "="*80)
        print("Simple Agent with Observability Demo")
        print("="*80 + "\n")

        # Run interactive loop
        print("Ask me anything! I can search the web with DuckDuckGo and use Context7 MCP tools.")
        print("Type 'quit' to exit.\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue

                # Run agent
                response = asyncio.run(_run_agent_async(agent, user_input))

                print(f"\nAgent: {response}\n")

            except EOFError:
                print("\n\nGoodbye!")
                break
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                logger.error(f"Error running agent: {e}")
                if "credit balance is too low" in str(e).lower():
                    print(
                        "\nError: Your Anthropic account does not currently have enough credits. "
                        "Add Anthropic credits or set OPENAI_API_KEY in .env to use the OpenAI fallback.\n"
                    )
                    continue
                print(f"\nError: {e}\n")
    finally:
        if mcp_client is not None:
            logger.info("Shutting down MCP client")
            try:
                mcp_client.stop(None, None, None)
            except Exception as e:
                logger.warning("Error while shutting down MCP client: %s", e)


if __name__ == "__main__":
    main()
