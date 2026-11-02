from pydantic import BaseModel, Field

from app.models import Memory
from app.schemas.memory import MemoryCreate
from app.tools.base import BaseTool, ToolContext, ToolResult


class RetrieveMemoryInput(BaseModel):
    query: str = Field(default="", max_length=200)


class DeleteMemoryInput(BaseModel):
    memory_id: int = Field(ge=1)


class SaveMemoryTool(BaseTool):
    name = "save_memory"
    description = "Save a fact or preference the user explicitly asked to remember."
    input_schema = MemoryCreate
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: MemoryCreate) -> ToolResult:
        memory = Memory(
            user_id=ctx.user.id,
            content=params.content,
            category=params.category,
            source="user_explicit",
        )
        ctx.db.add(memory)
        ctx.db.commit()
        ctx.db.refresh(memory)
        return ToolResult(
            success=True,
            message=f"Saved to memory: {memory.content}",
            data={"memory_id": memory.id},
        )


class RetrieveMemoryTool(BaseTool):
    name = "retrieve_memory"
    description = "Search saved memories by keyword. Empty query returns the most recent ones."
    input_schema = RetrieveMemoryInput
    requires_confirmation = False

    def execute(self, ctx: ToolContext, params: RetrieveMemoryInput) -> ToolResult:
        query = ctx.db.query(Memory).filter(Memory.user_id == ctx.user.id)
        if params.query:
            query = query.filter(Memory.content.ilike(f"%{params.query}%"))
        memories = query.order_by(Memory.created_at.desc()).limit(20).all()

        if not memories:
            return ToolResult(success=True, message="No matching memories.", data={"memories": []})

        lines = [f"- {m.content}" for m in memories]
        return ToolResult(
            success=True,
            message="Here's what I remember:\n" + "\n".join(lines),
            data={"memories": [{"id": m.id, "content": m.content, "category": m.category} for m in memories]},
        )


class DeleteMemoryTool(BaseTool):
    name = "delete_memory"
    description = "Delete a saved memory by its ID."
    input_schema = DeleteMemoryInput
    requires_confirmation = True

    def confirmation_prompt(self, params: DeleteMemoryInput) -> str:
        return f"delete memory #{params.memory_id}"

    def execute(self, ctx: ToolContext, params: DeleteMemoryInput) -> ToolResult:
        memory = ctx.db.get(Memory, params.memory_id)
        if memory is None or memory.user_id != ctx.user.id:
            return ToolResult(success=False, message="Memory not found.")
        content = memory.content
        ctx.db.delete(memory)
        ctx.db.commit()
        return ToolResult(
            success=True,
            message=f"Deleted memory: {content}",
            data={"memory_id": params.memory_id},
        )