import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.browser_agent.runner import run_browser_task
from app.browser_agent.runner_paths import BACKEND_DIR, SHOT_DIR
from app.database.session import SessionLocal, get_db
from app.models import User
from app.models.browser_agent import BrowserAgentApproval, BrowserAgentStep, BrowserAgentTask

router = APIRouter(prefix="/browser-agent", tags=["browser-agent"])


def _redact(value: str) -> str:
    """Remove obvious contact and payment-number patterns before persistence."""
    value = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+[.][A-Z]{2,}", "[redacted-email]", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<![0-9])(?:[+]?[0-9][0-9 .()]{8,}[0-9])(?![0-9])", "[redacted-number]", value)
    return value


class CreateBrowserTask(BaseModel):
    goal: str = Field(min_length=8, max_length=1000)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approve|deny)$")


def _task_payload(task, include_steps=False, db=None):
    result = {
        "id": task.id, "goal": task.goal, "status": task.status,
        "final_answer": task.final_answer, "memory_files": task.memory_files or [],
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }
    if include_steps and db is not None:
        rows = db.query(BrowserAgentStep).filter(
            BrowserAgentStep.task_id == task.id
        ).order_by(BrowserAgentStep.sequence.asc()).all()
        result["steps"] = [{
            "id": row.id, "sequence": row.sequence, "thought": row.thought,
            "action": row.action, "status": row.status, "details": row.details,
            "screenshot_url": f"/browser-agent/screenshots/{row.screenshot_path}" if row.screenshot_path else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in rows]
        approval = db.query(BrowserAgentApproval).filter(
            BrowserAgentApproval.task_id == task.id,
            BrowserAgentApproval.status == "pending",
        ).order_by(BrowserAgentApproval.id.desc()).first()
        result["approval"] = ({
            "id": approval.id, "action": approval.action,
            "summary": approval.summary, "status": approval.status,
            "expires_at": approval.expires_at.isoformat(),
        } if approval else None)
    return result


@router.get("/demo-site", response_class=HTMLResponse)
def demo_site():
    """Local mock flight catalogue. It never calls airline or payment services."""
    return HTMLResponse("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SkyDemo · Flight search</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#14213a;font:15px Inter,system-ui,sans-serif}
main{max-width:1040px;margin:0 auto;padding:48px 28px}.brand{font-weight:850;letter-spacing:-1px;font-size:24px}.brand span{color:#6e63e8}
.hero{margin:42px 0 28px}.eyebrow{font-size:11px;letter-spacing:2px;color:#6e63e8;font-weight:800}.hero h1{font-size:38px;letter-spacing:-1.6px;margin:12px 0}.hero p{color:#65728a}
.panel{background:white;border:1px solid #e2e7f0;border-radius:18px;padding:22px;box-shadow:0 12px 40px #17294a0c}
form{display:grid;grid-template-columns:1fr 1fr 1fr 1fr auto;gap:12px;align-items:end}label{font-size:11px;font-weight:800;color:#738097;display:grid;gap:8px}input,select{width:100%;height:46px;border:1px solid #dbe1eb;border-radius:10px;padding:0 12px;font:inherit;color:#14213a;background:white}
button{border:0;border-radius:10px;background:#6e63e8;color:white;font-weight:750;padding:14px 18px;cursor:pointer}.results{margin-top:26px}.flight-card{display:grid;grid-template-columns:1.1fr 1fr .75fr auto;gap:14px;align-items:center;padding:18px;margin:12px 0;background:#fff;border:1px solid #e2e7f0;border-radius:14px}.airline{font-weight:800}.flight-time{font-size:19px;font-weight:800;margin-top:5px}.route,.stops{font-size:12px;color:#758198;margin-top:5px}.price{font-size:21px;font-weight:850}.note{font-size:11px;color:#738097;margin-top:26px}.ok{background:#e8f8ef;color:#177346;border-radius:12px;padding:18px;margin-top:18px;font-weight:750;display:none}
@media(max-width:780px){form{grid-template-columns:1fr 1fr}.flight-card{grid-template-columns:1fr 1fr}.flight-card button{grid-column:span 2}}
</style></head><body><main>
<div class="brand">sky<span>demo</span> <small style="font-size:11px;color:#8792a5;font-weight:600;letter-spacing:1px">LOCAL TEST ENVIRONMENT</small></div>
<section class="hero"><div class="eyebrow">BROWSER AGENT SANDBOX</div><h1>Find your next flight.</h1><p>Sample inventory for demonstrating browser automation and human approval.</p></section>
<section class="panel"><form id="flight_search">
<label>FROM<input id="origin" value="Delhi" autocomplete="off"></label>
<label>TO<input id="destination" value="Mumbai" autocomplete="off"></label>
<label>DATE<input id="travel_date" type="date"></label>
<label>DEPARTURE<select id="time_window"><option value="morning">Morning</option><option value="afternoon">Afternoon</option><option value="evening" selected>Evening</option><option value="night">Night</option></select></label>
<button id="search_flights" type="submit">Search flights →</button>
</form></section><section class="results" id="results" aria-live="polite"></section>
<div class="note">Demo only · Flights, fares and holds are fictional. No airline, reservation, or payment provider is contacted.</div>
<div id="hold_confirmation" class="ok" aria-live="polite"></div>
</main><script>
const inventory=[
{id:"6e-6116",airline:"IndiGo · 6E 6116",originTime:"18:20",arrival:"20:30",price:4950,stops:"Non-stop · 2h 10m"},
{id:"ai-2503",airline:"Air India · AI 2503",originTime:"19:05",arrival:"21:15",price:5420,stops:"Non-stop · 2h 10m"},
{id:"qp-1352",airline:"Akasa Air · QP 1352",originTime:"20:10",arrival:"22:20",price:4650,stops:"Non-stop · 2h 10m"}
];
const date=document.querySelector("#travel_date");const tomorrow=new Date();tomorrow.setDate(tomorrow.getDate()+1);date.value=tomorrow.toISOString().slice(0,10);
document.querySelector("#flight_search").addEventListener("submit",e=>{
e.preventDefault();const from=document.querySelector("#origin").value.trim();const to=document.querySelector("#destination").value.trim();const d=document.querySelector("#travel_date").value;
if(!from||!to||!d)return;const esc=(s)=>String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");const route=esc(from.toUpperCase())+" → "+esc(to.toUpperCase());const list=inventory.map(x=>({...x,route})).sort((a,b)=>a.price-b.price);
document.querySelector("#results").innerHTML="<h2>Available demo flights</h2>"+list.map(x=>'<article class="flight-card" data-flight-card data-flight-id="'+x.id+'" data-price="'+x.price+'"><div><div class="airline">'+x.airline+'</div><div class="route">'+x.route+'</div></div><div><div class="flight-time">'+x.originTime+' → '+x.arrival+'</div><div class="stops">'+x.stops+'</div></div><div><div class="price">₹'+x.price.toLocaleString("en-IN")+'</div><div class="stops">Sample fare · '+d+'</div></div><button type="button" data-hold="'+x.id+'">Hold this option</button></article>').join("");
document.querySelectorAll("[data-hold]").forEach(btn=>btn.addEventListener("click",()=>{
document.querySelector("#hold_confirmation").style.display="block";document.querySelector("#hold_confirmation").textContent="Demo hold confirmed · "+btn.closest(".flight-card").querySelector(".airline").innerText+" · No real booking created.";
}));
});
</script></body></html>""")


@router.post("/tasks")
def create_task(payload: CreateBrowserTask, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = BrowserAgentTask(user_id=user.id, goal=_redact(payload.goal.strip()), status="queued", memory_files=[])
    db.add(task)
    db.commit()
    db.refresh(task)
    background.add_task(run_browser_task, task.id)
    return _task_payload(task)


@router.get("/tasks")
def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(BrowserAgentTask).filter(
        BrowserAgentTask.user_id == user.id
    ).order_by(BrowserAgentTask.created_at.desc()).limit(100).all()
    if not rows:
        now = datetime.now(timezone.utc)
        rows = [
            BrowserAgentTask(user_id=user.id, goal="[DEMO] Compare sample flights from Bengaluru to Goa", status="done", final_answer="Sample dashboard item: completed comparison; no booking.", memory_files=[], created_at=now - timedelta(hours=5)),
            BrowserAgentTask(user_id=user.id, goal="[DEMO] Check a hotel cancellation policy", status="failed", final_answer="Sample dashboard item: the demo target did not expose a cancellation policy.", memory_files=[], created_at=now - timedelta(hours=9)),
        ]
        db.add_all(rows)
        db.commit()
        for row in rows:
            db.refresh(row)
    return [_task_payload(row) for row in rows]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.query(BrowserAgentTask).filter(
        BrowserAgentTask.id == task_id, BrowserAgentTask.user_id == user.id
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_payload(task, include_steps=True, db=db)


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: int, user: User = Depends(get_current_user)):
    check = SessionLocal()
    try:
        task = check.query(BrowserAgentTask).filter(
            BrowserAgentTask.id == task_id, BrowserAgentTask.user_id == user.id
        ).first()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
    finally:
        check.close()

    async def events():
        last_id = 0
        idle_rounds = 0
        while idle_rounds < 1200:
            db = SessionLocal()
            try:
                task = db.query(BrowserAgentTask).filter(BrowserAgentTask.id == task_id).first()
                if not task:
                    break
                rows = db.query(BrowserAgentStep).filter(
                    BrowserAgentStep.task_id == task_id,
                    BrowserAgentStep.id > last_id,
                ).order_by(BrowserAgentStep.id.asc()).all()
                payload = {"task": _task_payload(task, include_steps=True, db=db), "steps": []}
                for row in rows:
                    payload["steps"].append({
                        "id": row.id, "sequence": row.sequence, "thought": row.thought,
                        "action": row.action, "status": row.status, "details": row.details,
                        "screenshot_url": f"/browser-agent/screenshots/{row.screenshot_path}" if row.screenshot_path else None,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    })
                    last_id = row.id
                yield "data: " + json.dumps(payload) + "\n\n"
                if task.status in {"done", "failed", "denied"}:
                    break
                idle_rounds = 0 if rows else idle_rounds + 1
            finally:
                db.close()
            await asyncio.sleep(0.6)

    return StreamingResponse(
        events(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/approvals/{approval_id}")
def decide_approval(approval_id: int, payload: ApprovalDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    approval = db.query(BrowserAgentApproval).join(BrowserAgentTask).filter(
        BrowserAgentApproval.id == approval_id, BrowserAgentTask.user_id == user.id,
    ).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="This approval is no longer pending")
    if approval.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        approval.status = "denied"
        approval.decided_at = datetime.now(timezone.utc)
        task = db.query(BrowserAgentTask).filter(BrowserAgentTask.id == approval.task_id).first()
        if task:
            task.status = "denied"
            task.final_answer = "Approval expired. The action was denied by default."
        db.commit()
        raise HTTPException(status_code=409, detail="Approval expired; action denied by default")
    approval.status = "approved" if payload.decision == "approve" else "denied"
    approval.decided_at = datetime.now(timezone.utc)
    db.commit()
    return {"approval_id": approval.id, "status": approval.status}


@router.get("/screenshots/{filename}")
def get_screenshot(filename: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    safe_name = Path(filename).name
    row = db.query(BrowserAgentStep).join(BrowserAgentTask).filter(
        BrowserAgentStep.screenshot_path == safe_name,
        BrowserAgentTask.user_id == user.id,
    ).first()
    path = SHOT_DIR / safe_name
    if not row or not path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/png", filename=safe_name)


@router.get("/memory")
def list_memory(user: User = Depends(get_current_user)):
    folder = BACKEND_DIR / "memory"
    return {"files": sorted(path.name for path in folder.glob("*.md"))}
