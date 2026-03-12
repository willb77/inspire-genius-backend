import asyncio
import os
import sys
from datetime import datetime
import json
import traceback

# Add project root to Python path to allow for module imports
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import only the function we want to test
from ai.ai_agent_services.agent_utils import get_assistant_helper
from ai.ai_agent_services.ai_tools import AssistantQuery

async def main():
    try:
        ai = await get_assistant_helper(user_input="how will william and mark work together?")
        print("Assistant response:")
        print(ai)
    except Exception as e:
        print(f"Error occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
