from typing import Annotated, TypedDict, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage
from sqlalchemy.orm import Session
from app.models.lead import Lead, LeadStage
from app.db.database import SessionLocal

class LeadAgentState(TypedDict):
    lead_id: int
    messages: list[BaseMessage]
    ml_score: float
    intent_flags: list[str]
    next_step: str

def evaluate_lead_node(state: LeadAgentState):
    """Evaluation logic to determine if lead is ready for handoff."""
    lead_id = state["lead_id"]
    score = state["ml_score"]
    
    # logic: check if student asked to book or has high score
    is_ready = score > 80 or "booking_request" in state["intent_flags"]
    
    return {"next_step": "handoff" if is_ready else "continue_ai"}

async def update_lead_db(lead_id: int, stage: LeadStage):
    """Helper to update lead stage in the database."""
    db: Session = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.stage = stage
            db.commit()
    finally:
        db.close()

async def execute_handoff_node(state: LeadAgentState):
    """Transition lead to human handoff."""
    await update_lead_db(state["lead_id"], LeadStage.HANDOFF)
    return state

# --- GRAPH DEFINITION ---

workflow = StateGraph(LeadAgentState)

# Add Nodes
workflow.add_node("evaluator", evaluate_lead_node)
workflow.add_node("handoff_trigger", execute_handoff_node)

# Set Entry
workflow.set_entry_point("evaluator")

# Conditional Edges
workflow.add_conditional_edges(
    "evaluator",
    lambda x: x["next_step"],
    {
        "handoff": "handoff_trigger",
        "continue_ai": END
    }
)

workflow.add_edge("handoff_trigger", END)

app = workflow.compile()