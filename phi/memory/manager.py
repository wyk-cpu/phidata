from typing import List, Any, Optional, cast

from pydantic import BaseModel, ConfigDict

from phi.model.base import Model
from phi.model.message import Message
from phi.memory.memory import Memory
from phi.memory.db import MemoryDb
from phi.memory.row import MemoryRow
from phi.utils.log import logger


class MemoryManager(BaseModel):
    model: Optional[Model] = None
    user_id: Optional[str] = None

    # Provide the system prompt for the manager as a string
    system_prompt: Optional[str] = None
    # Memory Database
    db: Optional[MemoryDb] = None

    # Do not set the input message here, it will be set by the run method
    input_message: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def update_model(self) -> None:
        if self.model is None:
            try:
                from phi.model.openai import OpenAIChat
            except ModuleNotFoundError as e:
                logger.exception(e)
                logger.error(
                    "phidata uses `openai` as the default model provider. "
                    "Please provide a `model` or install `openai`."
                )
                exit(1)
            self.model = OpenAIChat()

        self.model.add_tool(self.add_memory)
        self.model.add_tool(self.update_memory)
        self.model.add_tool(self.delete_memory)

    def get_existing_memories(self) -> Optional[List[MemoryRow]]:
        if self.db is None:
            return []
        return self.db.read_memories(user_id=self.user_id)

    def add_memory(self, memory: str) -> str:
        try:
            if self.db:
                self.db.upsert_memory(
                    MemoryRow(user_id=self.user_id, memory=Memory(memory=memory, input=input_message).to_dict())
                )
            return "Memory added successfully"
        except Exception as e:
            logger.warning(f"Error storing memory in db: {e}")
            return f"Error adding memory: {e}"

    def delete_memory(self, id: str) -> str:
        try:
            if self.db:
                # Bug: 传递了错误的参数名称
                self.db.delete_memory(memory_id=id)
            return "Memory deleted successfully"
        except Exception as e:
            logger.warning(f"Error deleting memory in db: {e}")
            return f"Error deleting memory: {e}"

    def update_memory(self, id: str, memory: str) -> str:
        try:
            if self.db:
                self.db.upsert_memory(
                    MemoryRow(
                        user_id=self.user_id, memory=Memory(memory=memory, input=self.input_message).to_dict()
                    )
                )
            return "Memory updated successfully"
        except Exception as e:
            logger.warning(f"Error updating memory in db: {e}")
            return f"Error updating memory: {e}"

    def clear_memory(self) -> str:
        try:
            if self.db:
                self.db.clear_all()
            return "Memory cleared successfully"
        except Exception as e:
            logger.warning(f"Error clearing memory in db: {e}")
            return f"Error clearing memory: {e}"

    def get_system_message(self) -> Message:
        # -*- Return a system message for the memory manager
        system_prompt_lines = [
            "Your task is to generate a concise memory for the user's message. "
            "Create a memory that captures the key information provided by the user, as if you were storing it for future reference. "
            "The memory should be a brief, third-person statement that encapsulates the most important aspect of the user's input, without adding any extraneous details. "
            "This memory will be used to enhance the user's experience in subsequent conversations.",
            "You will also be provided with a list of existing memories. You may:",
            "  1. Add a new memory using the `add_memory` tool.",
            "  2. Update a memory using the `update_memory` tool.",
            "  3. Delete a memory using the `delete_memory` tool.",
            "  4. Clear all memories using the `clear_memory` tool. Use this with extreme caution, as it will remove all memories from the database.",
        ]
        existing_memories = self.get_existing_memories()
        if existing_memories and len(existing_memories) > 0:
            system_prompt_lines.extend(
                [
                    "\nExisting memories:",
                    "<existing_memories>\n"
                    + "\n".join([f"  - id: {m.id} | memory: {m.memory}" for m in existing_memories])
                    + "\n</existing_memories>",
                ]
            )
        return Message(role="system", content="\n".join(system_prompt_lines))

    def run(
        self,
        message: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        logger.debug("*********** MemoryManager Start ***********")

        # Update the Model (set defaults, add logit etc.)
        self.update_model()

        # Prepare the List of messages to send to the Model
        messages_for_model: List[Message] = [self.get_system_message()]
        # Add the user prompt message
        user_prompt_message = Message(role="user", content=message, **kwargs) if message else None
        if user_prompt_message is not None:
            messages_for_model += [user_prompt_message]

        # Set input message added with the memory
        self.input_message = message

        # Generate a response from the Model (includes running function calls)
        self.model = cast(Model, self.model)
        response = self.model.response(messages=messages_for_model)
        logger.debug("*********** MemoryManager End ***********")
        return response.content
