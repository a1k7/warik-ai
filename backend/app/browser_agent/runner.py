"""Playwright runner for the local flight-search demonstration."""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.browser_agent.llm import call_model
from app.browser_agent.memory import select_memories
from app.browser_agent.runner_paths import BACKEND_DIR, SHOT_DIR
from app.core.config import settings
from app.database.session import SessionLocal
from app.models.browser_agent import BrowserAgentApproval, BrowserAgentStep, BrowserAgentTask

logger = logging.getLogger(__name__)
TOOLS = [
    {"name": "navigate", "description": "Open the allowlisted local flight demo"},
    {"name": "fill", "description": "Fill the flight search form"},
    {"name": "click", "description": "Search or select a flight"},
    {"name": "read_page", "description": "Read and compare visible flight results"},
    {"name": "ask_approval", "description": "Pause before holding a flight"},
]


def _route_from_goal(goal: str) -> tuple[str, str]:
    match = re.search(
        r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:tomorrow|today|tonight|on|for|next|and|with)\b|[,.]|$)",
        goal,
        re.IGNORECASE,
    )
    if not match:
        return "Delhi", "Mumbai"
    return (
        re.sub(r"\s+", " ", match.group(1)).strip(" .")[:60] or "Delhi",
        re.sub(r"\s+", " ", match.group(2)).strip(" .")[:60] or "Mumbai",
    )


def _plan(goal: str, memories: list[dict[str, str]]) -> dict:
    origin, destination = _route_from_goal(goal)
    if not settings.agent_demo_mode:
        context = "\n".join(item["content"] for item in memories)
        raw = call_model(
            [{"role": "user", "content": goal + "\n\nRelevant saved preferences:\n" + context}],
            TOOLS,
        )
        if raw:
            try:
                model_plan = json.loads(raw)
                return {
                    "origin": str(model_plan.get("origin") or origin)[:60],
                    "destination": str(model_plan.get("destination") or destination)[:60],
                    "plan_summary": str(model_plan.get("plan_summary") or "Search, compare, and request approval before holding the selected option.")[:240],
                    "mode": "configured_llm",
                }
            except (ValueError, TypeError):
                pass
    return {
        "origin": origin,
        "destination": destination,
        "plan_summary": "Search the local flight catalogue, compare fares, then pause for approval before the demo hold.",
        "mode": "scripted_demo",
    }


def _allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    allowed = {part.strip().lower() for part in settings.agent_allowed_domains.split(",") if part.strip()}
    return bool(host and host in allowed)


def _get_task(db, task_id: int):
    return db.query(BrowserAgentTask).filter(BrowserAgentTask.id == task_id).first()


def _add_step(db, task, thought: str, action: str, status: str = "completed", details: str | None = None, screenshot_path: str | None = None):
    sequence = db.query(BrowserAgentStep).filter(BrowserAgentStep.task_id == task.id).count() + 1
    row = BrowserAgentStep(
        task_id=task.id, sequence=sequence, thought=thought, action=action,
        status=status, details=details, screenshot_path=screenshot_path,
    )
    db.add(row)
    db.commit()
    return row


async def _capture(db, task, page, thought: str, action: str, status: str = "completed", details: str | None = None):
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    sequence = db.query(BrowserAgentStep).filter(BrowserAgentStep.task_id == task.id).count() + 1
    filename = f"task-{task.id}-step-{sequence}.png"
    try:
        await page.screenshot(path=str(SHOT_DIR / filename), full_page=True, animations="disabled")
        shot = filename
    except Exception:
        shot = None
    return _add_step(db, task, thought, action, status, details, shot)


def run_browser_task(task_id: int) -> None:
    """FastAPI BackgroundTasks entrypoint."""
    try:
        asyncio.run(_run(task_id))
    except Exception:
        logger.exception("Browser-agent task %s failed", task_id)
        db = SessionLocal()
        try:
            task = _get_task(db, task_id)
            if task:
                task.status = "failed"
                task.final_answer = "The browser session failed. Install Playwright Chromium and retry. See README for setup."
                db.commit()
        finally:
            db.close()


async def _run(task_id: int) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        db = SessionLocal()
        try:
            task = _get_task(db, task_id)
            if task:
                task.status = "failed"
                task.final_answer = "Playwright is not installed. Run: pip install -r requirements.txt && playwright install chromium"
                db.commit()
        finally:
            db.close()
        return

    db = SessionLocal()
    playwright = browser = page = None
    active_started = time.monotonic()
    try:
        task = _get_task(db, task_id)
        if not task:
            return
        task.status = "running"
        memories = select_memories(task.goal)
        task.memory_files = [item["file"] for item in memories]
        plan = _plan(task.goal, memories)
        db.commit()

        _add_step(
            db, task,
            "I converted your request into a flight-search plan and loaded relevant saved preferences.",
            "plan",
            details=json.dumps({"planner": plan["mode"], "summary": plan["plan_summary"], "memory_used": task.memory_files}),
        )

        base = settings.agent_demo_base_url.rstrip("/")
        target = base + "/api/browser-agent/demo-site"
        if not _allowed(target):
            raise RuntimeError("Navigation blocked: demo target is not in AGENT_ALLOWED_DOMAINS.")

        playwright = await async_playwright().start()
        if settings.agent_browser_cdp_url.strip():
            browser = await playwright.chromium.connect_over_cdp(settings.agent_browser_cdp_url.strip())
        else:
            browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)

        await page.goto(target, wait_until="domcontentloaded", timeout=30000)
        await _capture(db, task, page, "I opened the controlled flight-search site in a real Chromium browser.", "navigate", details=target)
        if time.monotonic() - active_started > settings.agent_timeout_seconds:
            raise TimeoutError("The 5-minute active browser execution limit was reached.")

        await page.locator("#origin").fill(plan["origin"])
        await page.locator("#destination").fill(plan["destination"])
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        await page.locator("#travel_date").fill(tomorrow)
        await page.locator("#time_window").select_option("evening")
        await _capture(
            db, task, page,
            f"I entered {plan['origin']} to {plan['destination']} for tomorrow evening.",
            "fill",
            details=json.dumps({"origin": plan["origin"], "destination": plan["destination"], "date": tomorrow, "time_window": "evening"}),
        )
        await page.locator("#search_flights").click()
        await page.locator(".flight-card").first.wait_for(timeout=10000)
        cards = await page.locator(".flight-card").evaluate_all(
            "(nodes) => nodes.map(n => ({id:n.dataset.flightId, airline:n.querySelector('.airline').innerText, route:n.querySelector('.route').innerText, price:Number(n.dataset.price), time:n.querySelector('.flight-time').innerText, stops:n.querySelector('.stops').innerText}))"
        )
        if not cards:
            raise RuntimeError("The demo flight catalogue returned no results.")
        cheapest = min(cards, key=lambda item: item["price"])
        await _capture(
            db, task, page,
            f"I compared {len(cards)} visible demo options and selected the lowest displayed fare.",
            "read_page",
            details=json.dumps({"options": cards, "selected": cheapest}),
        )
        await page.locator(f'[data-hold="{cheapest["id"]}"]').wait_for(state="visible")
        approval = BrowserAgentApproval(
            task_id=task.id,
            action="hold_demo_flight",
            summary=f"Hold {cheapest['airline']} {cheapest['route']} for ₹{cheapest['price']:,}? This is a local demo action; no real ticket or payment will be created.",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.agent_approval_timeout_seconds),
        )
        db.add(approval)
        task.status = "waiting_approval"
        db.commit()
        await _capture(
            db, task, page,
            "The next operation is a hold/submit action. I paused and am waiting for your approval.",
            "ask_approval",
            status="waiting_approval",
            details=json.dumps({"approval_id": approval.id, "action": approval.action, "summary": approval.summary}),
        )

        deadline = time.monotonic() + settings.agent_approval_timeout_seconds
        while time.monotonic() < deadline:
            db.refresh(approval)
            if approval.status in {"approved", "denied"}:
                break
            await asyncio.sleep(0.5)

        if approval.status == "pending":
            approval.status = "denied"
            approval.decided_at = datetime.now(timezone.utc)
            task.status = "denied"
            task.final_answer = "Approval expired after 10 minutes. The hold action was denied by default; nothing was submitted."
            db.commit()
            await _capture(db, task, page, "The approval window expired. The task stopped safely without submitting.", "approval_timeout", status="denied")
            return

        if approval.status != "approved":
            task.status = "denied"
            task.final_answer = "You denied the hold action. The browser stopped before submitting anything."
            db.commit()
            await _capture(db, task, page, "You denied the proposed hold. I stopped before the irreversible step.", "approval_denied", status="denied")
            return

        await page.locator(f'[data-hold="{cheapest["id"]}"]').click()
        await page.locator("#hold_confirmation").wait_for(state="visible")
        task.status = "done"
        task.final_answer = (
            f"Found {len(cards)} non-stop demo options. Cheapest: {cheapest['airline']} {cheapest['route']} at ₹{cheapest['price']:,}. "
            "Your approval was recorded and the local demo hold was completed. No real flight was booked or payment taken."
        )
        db.commit()
        await _capture(
            db, task, page,
            "Approval was received. I completed the mock hold on the local demo site and verified its confirmation.",
            "hold_demo_flight",
            details=task.final_answer,
        )
    except Exception as exc:
        logger.exception("Browser-agent execution failed")
        task = _get_task(db, task_id)
        if task:
            task.status = "failed"
            task.final_answer = f"Browser task failed: {str(exc)[:400]}"
            db.commit()
            if page:
                try:
                    await _capture(db, task, page, "The browser run stopped because an operation failed.", "error", status="failed", details=str(exc)[:400])
                except Exception:
                    pass
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if browser and not settings.agent_browser_cdp_url.strip():
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass
        db.close()
