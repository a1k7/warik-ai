from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import Memory, User
from app.schemas.memory import MemoryCreate, MemoryResponse, MemoryUpdate

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("/", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryResponse:
    memory = Memory(
        user_id=user.id,
        content=payload.content,
        category=payload.category,
        source="user_explicit",
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.get("/", response_model=list[MemoryResponse])
def list_memories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemoryResponse]:
    memories = (
        db.query(Memory)
        .filter(Memory.user_id == user.id)
        .order_by(Memory.created_at.desc())
        .all()
    )
    return [MemoryResponse.model_validate(m) for m in memories]


@router.put("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: int,
    payload: MemoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemoryResponse:
    memory = db.get(Memory, memory_id)
    if memory is None or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(memory, key, value)

    db.commit()
    db.refresh(memory)
    return MemoryResponse.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    memory = db.get(Memory, memory_id)
    if memory is None or memory.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")

    db.delete(memory)
    db.commit()


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_memories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Provide a hard privacy control: wipe all memories for this user."""
    db.query(Memory).filter(Memory.user_id == user.id).delete()
    db.commit()