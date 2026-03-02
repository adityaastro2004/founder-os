"""
Debug script: test the full agent chain for delete events.
Bypasses HTTP auth by directly instantiating the registry.
"""
import asyncio
import logging
import uuid

logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("debug_agent")

async def main():
    from app.config import get_settings
    from app.database import async_session
    from app.redis import init_redis
    from app.agents.registry import AgentRegistry

    settings = get_settings()
    redis = await init_redis()

    async with async_session() as db:
        registry = AgentRegistry(db=db, redis=redis, settings=settings)
        user_uuid = uuid.uuid5(uuid.NAMESPACE_URL, "clerk:test-debug")

        planner_uid = "default-user"
        logger.info("=== Building planner agent with planner_uid=%s ===", planner_uid)

        agent = await registry.get(
            "planner",
            user_id=user_uuid,
            session_id="debug-session",
            planner_user_id=planner_uid,
        )

        # Check what tools are available
        tool_schemas = await agent.tools.list_tools()
        tool_names = [t.name for t in tool_schemas]
        logger.info("=== Available tools (%d): %s ===", len(tool_names), tool_names)

        gcal_tools = [t for t in tool_names if t.startswith("gcal_")]
        logger.info("=== GCal tools: %s ===", gcal_tools)

        if not gcal_tools:
            logger.error("!!! NO GCAL TOOLS AVAILABLE — MCP provider not loaded !!!")
            return

        # Test: Ask the agent to list events (simpler than delete, saves quota)
        logger.info("=== Test: Ask agent to list calendar events ===")
        agent_result = await agent.run("What events do I have tomorrow?")
        logger.info("Agent response: %s", agent_result.content[:1000])
        logger.info("Tool calls made: %d", len(agent_result.tool_calls_made))
        for tc in agent_result.tool_calls_made:
            logger.info("  Tool: %s, error=%s", tc.get("tool"), tc.get("is_error"))

if __name__ == "__main__":
    asyncio.run(main())
