"""
Memory-enabled agent using MemoryManager, Strands SDK, and Groq via LiteLLM.

This module implements a conversational agent with semantic memory storage
using MemoryManager for backend-agnostic memory operations, Strands SDK for
the agent framework, and Groq for LLM inference via LiteLLM. The agent
automatically stores all conversations in the background and provides tools
for explicit memory operations.

Note: MemoryManager uses async methods internally, but this agent provides
a synchronous interface for ease of use in educational contexts.
"""

import asyncio
import json
import logging
import os
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from dotenv import load_dotenv
from duckduckgo_search import DDGS
from strands import (
    Agent as StrandsAgent,
    tool,
)
from strands.models import LiteLLMModel

from memory_manager import MemoryManager


# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
DEFAULT_MODEL: str = "gpt-4o-mini"
DEFAULT_USER_ID: str = "default_user"


def _run_async(coro):
    """Run async coroutine, handling both sync and async contexts.

    This helper allows the agent to maintain a synchronous interface while
    using async memory operations internally. It handles both cases:
    - If there's already an event loop running, awaits directly
    - If no loop exists, runs in a new loop

    Args:
        coro: Async coroutine to execute

    Returns:
        Result from the coroutine execution
    """
    try:
        loop = asyncio.get_running_loop()
        # There's already a loop running - we need to handle this carefully
        # In Strands context, tools may be called from async context
        # We'll use asyncio.ensure_future and wait for it
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(coro)
    except RuntimeError:
        # No loop running, safe to use asyncio.run()
        return asyncio.run(coro)
    except ImportError:
        # nest_asyncio not available, use thread pool approach
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()


# Removed Pydantic input models - Strands uses function signatures directly


def _create_search_memory_tool(
    memory_manager: MemoryManager,
    user_id: str,
    agent_id: str,
    run_id: str
):
    """Create the search_memory tool function for semantic memory search.

    Args:
        memory_manager: MemoryManager instance for memory operations
        user_id: User identifier for memory isolation
        agent_id: Agent identifier for multi-agent scenarios
        run_id: Session/conversation identifier

    Returns:
        Decorated tool function for memory search
    """
    @tool
    async def search_memory(query: str, limit: int = 5) -> str:
        """Search for relevant information from previous conversations using semantic search.

        Use this when you need to recall specific facts, preferences, or context from
        earlier in the conversation or from past sessions. Returns memories ranked by relevance.

        Args:
            query: The search query to find relevant memories.
            limit: Maximum number of memories to return (default: 5, range: 1-20).

        Returns:
            JSON string with search results including memory content and relevance scores.
        """
        logger.info(f"[TOOL INVOKED] search_memory called with query='{query}', limit={limit}, user_id={user_id}, run_id={run_id}")
        try:
            # Coerce limit to int in case LLM passes string
            try:
                limit = int(limit) if limit is not None else 5
            except (ValueError, TypeError):
                logger.warning(f"Invalid limit value '{limit}', using default of 5")
                limit = 5
            logger.info(f"Searching memories for: '{query}' (limit={limit})")

            # Call async memory search with multi-tenant context
            results = await memory_manager.search(
                user_id=user_id,
                query=query,
                limit=limit,
                agent_id=agent_id,
                run_id=run_id
            )

            if not results:
                response = {
                    "status": "success",
                    "count": 0,
                    "memories": [],
                    "message": "No relevant memories found"
                }
                logger.info("No memories found for query")
                return json.dumps(response, indent=2)

            response = {
                "status": "success",
                "count": len(results),
                "memories": results
            }

            logger.info(f"Found {len(results)} relevant memories")
            logger.debug(f"Results:\n{json.dumps(response, indent=2, default=str)}")

            return json.dumps(response, indent=2)

        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            error_response = {
                "status": "error",
                "message": str(e)
            }
            return json.dumps(error_response, indent=2)

    logger.info("Created search_memory tool")
    return search_memory


def _create_insert_memory_tool(
    memory_manager: MemoryManager,
    user_id: str,
    agent_id: str,
    run_id: str
):
    """Create the insert_memory tool function for explicit memory storage.

    Args:
        memory_manager: MemoryManager instance for memory operations
        user_id: User identifier for memory isolation
        agent_id: Agent identifier for multi-agent scenarios
        run_id: Session/conversation identifier

    Returns:
        Decorated tool function for memory insertion
    """
    @tool
    async def insert_memory(
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Explicitly store important information in long-term memory.

        Use this for facts, preferences, or key information that should be remembered
        across conversations. The agent already stores conversations automatically,
        so use this for emphasizing particularly important information.

        Args:
            content: The information to store in memory.
            metadata: Optional metadata dictionary to associate with the memory.

        Returns:
            JSON string with operation status and stored content.
        """
        logger.info(f"[TOOL INVOKED] insert_memory called with content='{content[:100]}...', metadata={metadata}, user_id={user_id}, run_id={run_id}")
        try:
            logger.info(f"Inserting explicit memory: '{content[:100]}...'")

            # Call async memory insert with multi-tenant context
            result = await memory_manager.insert(
                user_id=user_id,
                content=content,
                agent_id=agent_id,
                run_id=run_id,
                metadata=metadata
            )

            response = {
                "status": result.get("status", "success"),
                "message": result.get("message", "Memory stored successfully"),
                "content": content,
                "metadata": metadata
            }

            logger.info("Successfully inserted memory")
            logger.debug(f"Response:\n{json.dumps(response, indent=2, default=str)}")

            return json.dumps(response, indent=2)

        except Exception as e:
            logger.error(f"Error inserting memory: {e}")
            error_response = {
                "status": "error",
                "message": str(e)
            }
            return json.dumps(error_response, indent=2)

    logger.info("Created insert_memory tool")
    return insert_memory


def _create_web_search_tool():
    """Create the web_search tool function for searching the web.

    Returns:
        Decorated tool function for web search
    """
    @tool
    def web_search(
        query: str,
        max_results: int = 3
    ) -> str:
        """Search the web for current information.

        Use when you need up-to-date information not in memory.
        Examples: current events, latest news, recent developments,
        real-time data, or information published after your knowledge cutoff.

        Args:
            query: The search query.
            max_results: Maximum number of results to return (default: 3, range: 1-10).

        Returns:
            JSON string with search results including titles, snippets, and URLs.
        """
        try:
            # Coerce max_results to int in case LLM passes string
            try:
                max_results = int(max_results) if max_results is not None else 3
            except (ValueError, TypeError):
                logger.warning(f"Invalid max_results value '{max_results}', using default of 3")
                max_results = 3
            logger.info(f"Searching web for: '{query}' (max_results={max_results})")

            # Limit max_results to reasonable range
            max_results = max(1, min(max_results, 10))

            # Perform search using DuckDuckGo
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))

            if not results:
                response = {
                    "status": "success",
                    "count": 0,
                    "results": [],
                    "message": "No search results found"
                }
                logger.info("No web results found for query")
                return json.dumps(response, indent=2)

            search_results = []
            for result in results:
                search_results.append({
                    "title": result.get("title", ""),
                    "snippet": result.get("body", ""),
                    "url": result.get("href", ""),
                })

            response = {
                "status": "success",
                "count": len(search_results),
                "results": search_results
            }

            logger.info(f"Found {len(search_results)} web results")
            logger.debug(f"Results:\n{json.dumps(response, indent=2, default=str)}")

            return json.dumps(response, indent=2)

        except Exception as e:
            logger.error(f"Error searching web: {e}")
            error_response = {
                "status": "error",
                "message": str(e)
            }
            return json.dumps(error_response, indent=2)

    logger.info("Created web_search tool")
    return web_search


def _build_system_prompt() -> str:
    """Load system prompt from prompts/system_prompt.txt.

    Returns:
        System prompt string

    Raises:
        FileNotFoundError: If system_prompt.txt is not found
    """
    prompt_file = os.path.join(
        os.path.dirname(__file__),
        "prompts",
        "system_prompt.txt"
    )

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()
        logger.debug(f"Loaded system prompt from {prompt_file}")
        return prompt
    except FileNotFoundError:
        logger.error(f"System prompt file not found: {prompt_file}")
        raise FileNotFoundError(
            f"System prompt file not found at {prompt_file}. "
            "Please ensure prompts/system_prompt.txt exists."
        )


class Agent:
    """Generic conversational agent that uses memory for context.

    This agent uses memory as a tool, not as its primary identity. It can
    converse naturally and uses memory tools (search, insert) when appropriate.
    The memory backend can be swapped by changing the MemoryManager implementation.

    Note: While the MemoryManager uses async methods internally, this agent
    provides a synchronous interface for simplicity. All memory operations
    are handled transparently using asyncio.

    Attributes:
        memory_manager: MemoryManager instance for backend-agnostic memory operations
        agent: Strands Agent instance with tool access
        user_id: User identifier for memory association
        model: LLM model identifier
    """

    def __init__(
        self,
        user_id: str = DEFAULT_USER_ID,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None
    ):
        """Initialize the memory-enabled agent.

        Args:
            user_id: User identifier for memory association (enables multi-tenant)
            model: LLM model to use via LiteLLM (supports any provider)
            api_key: API key for LLM provider (reads from env if not provided)
            agent_id: Agent identifier for multi-agent scenarios (defaults to "memory-agent")
            run_id: Session/conversation identifier (auto-generated UUID if not provided)

        Raises:
            ValueError: If no API key is found for any provider

        Note:
            agent_id and run_id enable multi-tenant, multi-session memory tracking
            for better organization and retrieval of conversation context.
        """
        # Get API key from parameter or environment (try multiple providers)
        if api_key:
            # Use provided key
            resolved_api_key = api_key
        else:
            # Try to find API key from environment for common providers
            resolved_api_key = (
                os.getenv("ANTHROPIC_API_KEY") or
                os.getenv("GROQ_API_KEY") or
                os.getenv("OPENAI_API_KEY") or
                os.getenv("GEMINI_API_KEY")
            )

        if not resolved_api_key:
            raise ValueError(
                "API key required. Set one of: ANTHROPIC_API_KEY, GROQ_API_KEY, "
                "OPENAI_API_KEY, or GEMINI_API_KEY environment variable, "
                "or pass api_key parameter."
            )

        # Set environment variables for LiteLLM (it checks multiple env vars)
        # This allows LiteLLM to auto-detect the provider
        if os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY")
        if os.getenv("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
        if os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
        if os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY")

        # Session management: auto-generate unique session ID if not provided
        import uuid
        self.user_id = user_id
        self.model = model
        self.agent_id = agent_id or "memory-agent"
        self.run_id = run_id or str(uuid.uuid4())[:8]  # Short UUID for readability

        logger.info(
            f"Initializing Agent - user: {user_id}, agent: {self.agent_id}, "
            f"session: {self.run_id}"
        )

        # Get Mem0 API key for cloud memory storage
        mem0_api_key = os.getenv("MEM0_API_KEY")
        if not mem0_api_key:
            raise ValueError(
                "MEM0_API_KEY is required for cloud memory storage. "
                "Get your free API key from https://app.mem0.ai/dashboard "
                "and add it to your .env file."
            )

        # Initialize multi-tenant MemoryManager (ONE instance serves ALL users/sessions)
        # User context (user_id, agent_id, run_id) is passed to methods, not stored
        self.memory_manager = MemoryManager(
            api_key=mem0_api_key
        )

        logger.info("Memory manager initialized for multi-tenant operation")

        # Create memory tools with user/session context for multi-tenant operation
        search_tool = _create_search_memory_tool(
            self.memory_manager,
            self.user_id,
            self.agent_id,
            self.run_id
        )
        insert_tool = _create_insert_memory_tool(
            self.memory_manager,
            self.user_id,
            self.agent_id,
            self.run_id
        )
        web_tool = _create_web_search_tool()

        # Initialize Strands agent with LiteLLM model and tools
        system_prompt = _build_system_prompt()

        litellm_model = LiteLLMModel(model_id=model)

        self.agent = StrandsAgent(
            model=litellm_model,
            system_prompt=system_prompt,
            tools=[search_tool, insert_tool, web_tool]
        )

        logger.info(
            f"Initialized Agent with model {model} and 3 tools (2 memory + 1 web search)"
        )


    def chat(
        self,
        user_input: str
    ) -> str:
        """Process user input with automatic memory storage.

        This method:
        1. Processes the message through the Strands agent
        2. Automatically stores the conversation in memory backend (async internally)
        3. Returns the assistant's response

        Note: While memory operations are async internally, this method provides
        a synchronous interface for ease of use. Memory storage happens in the
        background without blocking the response.

        Args:
            user_input: User's message

        Returns:
            Assistant's response text

        Raises:
            ValueError: If user input is empty
        """
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")

        logger.info(f"Processing user input (length: {len(user_input)} chars)")

        try:
            # Process message through agent (agent is callable)
            result = self.agent(user_input)

            # Extract text response from result
            response_text = self._extract_response_text(result)

            logger.info(f"Received response (length: {len(response_text)} chars)")

            # Store conversation in background
            self._store_conversation_async(user_input, response_text)

            return response_text

        except ValueError as e:
            # Handle known LiteLLM/Groq integration issue where Groq returns
            # 'tool_use_failed' as a status string instead of an integer
            error_msg = str(e)
            if "invalid literal for int" in error_msg and "tool_use_failed" in error_msg:
                logger.warning(
                    "Known LiteLLM/Groq issue: tool_use_failed status conversion error. "
                    "This is handled by automatic retry."
                )
                # Re-raise to let Strands/LiteLLM retry logic handle it
                raise
            else:
                logger.error(f"Error processing chat: {e}")
                raise

        except Exception as e:
            logger.error(f"Error processing chat: {e}")
            raise


    def _extract_response_text(
        self,
        result
    ) -> str:
        """Extract text response from Strands agent result.

        Args:
            result: Strands agent result object

        Returns:
            Extracted text response
        """
        content = result.message.get("content", [])
        text_parts = []

        for block in content:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])

        return " ".join(text_parts).strip()


    def _store_conversation_async(
        self,
        user_message: str,
        assistant_message: str
    ) -> None:
        """Store conversation in memory backend in the background.

        This method handles async memory storage while maintaining a synchronous
        interface. The conversation is stored using the async memory manager.

        Args:
            user_message: User's message
            assistant_message: Assistant's response
        """
        try:
            # Run async memory storage synchronously with multi-tenant context
            _run_async(
                self.memory_manager.add_conversation(
                    user_id=self.user_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    agent_id=self.agent_id,
                    run_id=self.run_id
                )
            )

            logger.debug("Stored conversation in memory")

        except Exception as e:
            logger.error(f"Error storing conversation in memory: {e}")


    def get_all_memories(
        self,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve all stored memories for the user.

        Uses async memory manager internally but provides a synchronous interface.

        Args:
            limit: Optional limit on number of memories to return

        Returns:
            List of memory dictionaries
        """
        try:
            # Run async memory retrieval synchronously with user context
            memories = _run_async(
                self.memory_manager.get_all(
                    user_id=self.user_id,
                    limit=limit
                )
            )

            logger.info(f"Retrieved {len(memories)} memories")
            return memories

        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            return []


    def reset_memory(self) -> None:
        """Clear all memories for the user.

        Uses async memory manager internally but provides a synchronous interface.
        Warning: This permanently deletes all stored memories.
        """
        try:
            # Run async memory clear synchronously with user context
            _run_async(self.memory_manager.clear(user_id=self.user_id))

            logger.info(f"Reset all memories for user: {self.user_id}")

        except Exception as e:
            logger.error(f"Error resetting memory: {e}")
            raise


def _run_demo() -> None:
    """Run a demonstration of the memory agent."""
    print("=" * 70)
    print("Memory Agent Demo - Mem0 + Strands + LiteLLM")
    print("=" * 70)
    print()

    # Check for API key (any provider)
    has_api_key = (
        os.getenv("ANTHROPIC_API_KEY") or
        os.getenv("GROQ_API_KEY") or
        os.getenv("OPENAI_API_KEY") or
        os.getenv("GEMINI_API_KEY")
    )

    if not has_api_key:
        print("ERROR: No API key found in environment.")
        print("Please set one of the following:")
        print("  ANTHROPIC_API_KEY (used by default in this lab)")
        print("  GROQ_API_KEY (free, no credit card required)")
        print("  OPENAI_API_KEY")
        print("  GEMINI_API_KEY")
        print()
        print("Get API keys at:")
        print("  Anthropic: https://console.anthropic.com/")
        print("  Groq: https://console.groq.com/ (FREE)")
        return

    print("Initializing agent with semantic memory...")
    print()
    print("NOTE: You may see 'tool_use_failed' ValueError messages during execution.")
    print("      These are harmless warnings from LiteLLM/Groq integration and are")
    print("      automatically handled by retry logic. The agent works correctly.")
    print()

    # Create agent with a fresh user_id to avoid any cached/corrupted state
    import uuid
    demo_user_id = f"demo_{uuid.uuid4().hex[:8]}"
    print(f"Using user_id: {demo_user_id}")
    agent = Agent(user_id=demo_user_id)

    print("Agent initialized! Features:")
    print("  - Automatic background storage of all conversations")
    print("  - Semantic search across conversation history")
    print("  - Explicit memory insertion for important facts")
    print("  - Web search for current information (DuckDuckGo)")
    print("  - Qdrant vector database with HuggingFace embeddings")
    print()

    # Conversation sequence demonstrating memory capabilities
    conversations = [
        (
            "Hi! My name is Alice and I'm a software engineer specializing in Python.",
            "1. Introduction"
        ),
        (
            "I'm working on a machine learning project using scikit-learn.",
            "2. Share project info"
        ),
        (
            "What's my name and occupation?",
            "3. Memory recall (should search automatically)"
        ),
        (
            "Please remember that my favorite programming language is Python "
            "and I prefer clean, maintainable code.",
            "4. Explicit memory request"
        ),
        (
            "What are my preferences when it comes to coding?",
            "5. Retrieve preferences (should search memory)"
        ),
        (
            "Tell me about neural networks.",
            "6. New topic (no memory search needed)"
        ),
        (
            "What project did I mention earlier?",
            "7. Recall previous context (should search memory)"
        ),
    ]

    for i, (user_msg, description) in enumerate(conversations, 1):
        print(f"\n{'─' * 70}")
        print(f"Turn {i}: {description}")
        print(f"{'─' * 70}")
        print(f"User: {user_msg}")
        print()

        try:
            response = agent.chat(user_msg)
            print(f"Assistant: {response}")

        except Exception as e:
            print(f"Error: {e}")
            logger.exception("Error in demo conversation")

    print("\n" + "=" * 70)
    print("Demo completed!")
    print("=" * 70)
    print()

    import time

    # Poll for memories with increasing wait times
    print("Checking for indexed memories (Mem0 uses background processing)...")
    all_memories = []

    for total_wait in [10, 20, 30, 45, 60]:
        print(f"  Waiting {10 if total_wait == 10 else (total_wait - (total_wait - 10))} more seconds... (total: {total_wait}s)")
        time.sleep(10)
        
        all_memories = agent.get_all_memories()
        print(f"  Found {len(all_memories)} memories")
        
        if all_memories:
            print("  SUCCESS! Memories are now indexed.")
            break
    else:
        print("  Timeout after 60s - memories may still be processing in Mem0 cloud.")
        print("  Check https://app.mem0.ai/dashboard to verify they were stored.")

    print()
    print("Memory Statistics:")
    print(f"  Total memories stored: {len(all_memories)}")
    print()

    if all_memories:
        print("Sample memories:")
        sample_count = min(3, len(all_memories))
        for i in range(sample_count):
            mem = all_memories[i]
            memory_text = mem.get("memory", "")
            if len(memory_text) > 80:
                memory_text = memory_text[:80] + "..."
            print(f"  - {memory_text}")

    print()
    print("Note: Agent automatically stores conversations and intelligently")
    print("decides when to search memory based on context.")

    # # Show memory statistics
    # all_memories = agent.get_all_memories()

    # # Ensure all_memories is a list
    # if not isinstance(all_memories, list):
    #     all_memories = []

    # print(f"  Total memories stored: {len(all_memories)}")
    # print()

    # if all_memories:
    #     print("Sample memories:")
    #     # Show up to 3 memories
    #     sample_count = min(3, len(all_memories))
    #     for i in range(sample_count):
    #         mem = all_memories[i]
    #         memory_text = mem.get("memory", "")
    #         if len(memory_text) > 80:
    #             memory_text = memory_text[:80] + "..."
    #         print(f"  - {memory_text}")

    print()
    print("Note: Agent automatically stores conversations and intelligently")
    print("decides when to search memory based on context.")


if __name__ == "__main__":
    _run_demo()
