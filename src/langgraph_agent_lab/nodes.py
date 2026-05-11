"""Node skeletons for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

from .state import AgentState, ApprovalDecision, Route, make_event


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.

    TODO(student): add normalization, PII checks, and metadata extraction.
    """
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route.

    Priority order: RISKY > TOOL > ERROR > MISSING_INFO > SIMPLE.
    This prevents keyword conflicts (e.g., "check order for refund" → risky, not tool).
    """
    query = state.get("query", "").lower()
    words = query.split()
    clean_words = [w.strip("?!.,;:") for w in words]
    
    route = Route.SIMPLE
    risk_level = "low"
    
    # Priority 1: RISKY keywords (highest priority - destructive actions)
    risky_keywords = ["refund", "delete", "remove", "cancel", "send", "revoke"]
    if any(kw in query for kw in risky_keywords):
        route = Route.RISKY
        risk_level = "high"
    # Priority 2: TOOL keywords (external lookup needed)
    elif any(kw in query for kw in ["status", "order", "lookup", "check", "track", "find", "search"]):
        route = Route.TOOL
        risk_level = "low"
    # Priority 3: ERROR keywords (transient/system failures)
    elif any(kw in query for kw in ["timeout", "fail", "error", "crash", "unavailable"]):
        route = Route.ERROR
        risk_level = "low"
    # Priority 4: MISSING_INFO (vague queries - very short with pronouns)
    elif len(clean_words) < 5 and "it" in clean_words:
        route = Route.MISSING_INFO
        risk_level = "low"
    # Priority 5: SIMPLE (default - safe responses)
    
    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    TODO(student): generate a specific clarification question from state.
    """
    question = "Can you provide the order id or the missing context?"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool.

    Simulates transient failures for error-route scenarios to demonstrate retry loops.
    TODO(student): implement idempotent tool execution and structured tool results.
    """
    attempt = int(state.get("attempt", 0))
    if state.get("route") == Route.ERROR.value and attempt < 2:
        result = f"ERROR: transient failure attempt={attempt} scenario={state.get('scenario_id', 'unknown')}"
    else:
        result = f"mock-tool-result for scenario={state.get('scenario_id', 'unknown')}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval.

    TODO(student): create a proposed action with evidence and risk justification.
    """
    return {
        "proposed_action": "prepare refund or external action; approval required",
        "events": [make_event("risky_action", "pending_approval", "approval required")],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.

    TODO(student): implement reject/edit decisions and timeout escalation.
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt or fallback decision.

    TODO(student): implement bounded retry, exponential backoff metadata, and fallback route.
    """
    attempt = int(state.get("attempt", 0)) + 1
    errors = [f"transient failure attempt={attempt}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [make_event("retry", "completed", "retry attempt recorded", attempt=attempt)],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response.

    TODO(student): ground the answer in tool_results and approval where relevant.
    """
    if state.get("tool_results"):
        answer = f"I found: {state['tool_results'][-1]}"
    else:
        answer = "This is a safe mock answer. Replace with your agent response."
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool result to decide retry vs success.

    This is the key retry-loop gate: checks if tool result indicates success or needs retry.
    """
    tool_results = state.get("tool_results", [])
    if not tool_results:
        return {"evaluation_result": "success"}
    
    last_result = tool_results[-1]
    
    # If result contains ERROR keyword and attempt < max_attempts, mark for retry
    if "ERROR:" in last_result and int(state.get("attempt", 0)) < int(state.get("max_attempts", 3)):
        evaluation_result = "needs_retry"
    else:
        evaluation_result = "success"
    
    return {
        "evaluation_result": evaluation_result,
        "events": [make_event("evaluate", "completed", f"evaluation={evaluation_result}")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log failure when max retries exhausted.

    Called when attempt >= max_attempts and retry loop cannot continue.
    """
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    errors = state.get("errors", [])
    
    message = f"Dead letter: exhausted {attempt} attempts (max={max_attempts})"
    return {
        "final_answer": f"Unable to resolve after {attempt} attempts. Escalating to support team.",
        "errors": errors + [message],
        "events": [make_event("dead_letter", "exhausted", message)],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the response and prepare for output.

    All paths converge here before END.
    """
    scenario_id = state.get("scenario_id", "unknown")
    route = state.get("route", "unknown")
    final_answer = state.get("final_answer", "No answer generated")
    
    return {
        "final_answer": final_answer,
        "events": [make_event("finalize", "completed", f"scenario={scenario_id} route={route}")],
    }
