# ruff: noqa
import datetime
import json
import re
import logging
import sys
import os
from typing import List, Optional, Any

from google.adk.agents import Agent, LlmAgent  # type: ignore
from google.adk.apps import App, ResumabilityConfig  # type: ignore
from google.adk.models import Gemini  # type: ignore
from google.adk.tools import AgentTool  # type: ignore
from google.adk.tools.mcp_tool import McpToolset  # type: ignore
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams  # type: ignore
from mcp import StdioServerParameters  # type: ignore
from google.adk.workflow import Workflow, FunctionNode, START, node  # type: ignore
from google.adk.events.event import Event  # type: ignore
from google.adk.events.request_input import RequestInput  # type: ignore
from google.adk.agents.context import Context  # type: ignore
from google.genai import types  # type: ignore
from pydantic import BaseModel, Field

from .config import config

# --- 1. Schemas & Data Models ---

class Transaction(BaseModel):
    description: str
    amount: float
    category: str

class CategorizationReport(BaseModel):
    categorized_transactions: List[Transaction] = Field(default_factory=list)
    total_spent: float = 0.0
    budget_alerts: List[str] = Field(default_factory=list)

class SavingsReport(BaseModel):
    savings_goal: float = 0.0
    estimated_savings: float = 0.0
    suggestions: List[str] = Field(default_factory=list)

class OrchestratorReport(BaseModel):
    summary: str = ""
    needs_human_approval: bool = False
    categorization: CategorizationReport = Field(default_factory=CategorizationReport)
    savings: SavingsReport = Field(default_factory=SavingsReport)


# --- 2. MCP Toolset Setup ---

mcp_connection = StdioConnectionParams(
    server_params=StdioServerParameters(
        command=sys.executable,
        args=["-u", os.path.join(os.path.dirname(__file__), "mcp_server.py")]
    )
)
mcp_toolset = McpToolset(connection_params=mcp_connection)


# --- 3. Specialized LLM Sub-Agents ---

categorizer_agent = LlmAgent(
    name="categorizer_agent",
    model=Gemini(model=config.model),
    instruction="""You are an expense categorization specialist.
    Analyze the recent transaction list and match them against the budget limits.
    Classify any uncategorized transactions and flag any categories where the spending exceeds the budget.
    Use the tools in the MCP toolset to retrieve transaction and budget data.""",
    tools=[mcp_toolset],
    description="Categorizes transactions and analyzes budget status."
)

savings_agent = LlmAgent(
    name="savings_agent",
    model=Gemini(model=config.model),
    instruction="""You are a savings and investment specialist.
    Review the user's spending trends and savings goals.
    Formulate actionable suggestions to optimize savings and project estimated savings for the month.
    Use the tools in the MCP toolset to retrieve savings goal data.""",
    tools=[mcp_toolset],
    description="Analyzes savings goals and provides financial optimization tips."
)

categorizer_parser = LlmAgent(
    name="categorizer_parser",
    model=Gemini(model=config.model),
    instruction="""You are a data extraction specialist.
    Analyze the input text and extract:
    - The list of transactions, including their description, amount, and category.
    - The total spent.
    - Any budget alerts.
    Always format the output matching the requested output schema.""",
    output_schema=CategorizationReport,
    description="Parses expense categorization reports into structured JSON."
)

savings_parser = LlmAgent(
    name="savings_parser",
    model=Gemini(model=config.model),
    instruction="""You are a data extraction specialist.
    Analyze the input text and extract:
    - The savings goal.
    - The estimated savings.
    - Actionable suggestions for the user.
    Always format the output matching the requested output schema.""",
    output_schema=SavingsReport,
    description="Parses savings reports into structured JSON."
)


# --- 4. Orchestrator Node ---

@node(rerun_on_resume=True)
async def orchestrator_node(ctx: Context, node_input: types.Content) -> Event:
    """Orchestrates financial planning, categorization, and savings analysis by running sub-agents."""
    # 1. Run the categorizer agent to process transactions (plain text output)
    cat_raw = await ctx.run_node(categorizer_agent, node_input=node_input)
    # 2. Parse raw text into structured JSON
    cat_event = await ctx.run_node(categorizer_parser, node_input=cat_raw)
    if isinstance(cat_event, dict):
        cat_report = CategorizationReport(**cat_event)
    elif isinstance(cat_event, CategorizationReport):
        cat_report = cat_event
    else:
        cat_report = CategorizationReport()

    # 3. Run the savings agent to generate savings recommendations (plain text output)
    sav_raw = await ctx.run_node(savings_agent, node_input=node_input)
    # 4. Parse raw text into structured JSON
    sav_event = await ctx.run_node(savings_parser, node_input=sav_raw)
    if isinstance(sav_event, dict):
        sav_report = SavingsReport(**sav_event)
    elif isinstance(sav_event, SavingsReport):
        sav_report = sav_event
    else:
        sav_report = SavingsReport()

    # 5. Compute limits for human approval
    needs_approval = False
    for tx in cat_report.categorized_transactions:
        if tx.amount >= 500.0:
            needs_approval = True
            
    if cat_report.total_spent > 1500.0:
        needs_approval = True

    # 6. Generate final summary
    summary = f"Aggregated financial report for user transaction and savings profile."
    if cat_report.budget_alerts:
        summary += f" Budget limits exceeded in categories: {', '.join(cat_report.budget_alerts)}."
    else:
        summary += " All category budgets are within limits."

    report = OrchestratorReport(
        summary=summary,
        needs_human_approval=needs_approval,
        categorization=cat_report,
        savings=sav_report
    )
    
    # Save the output to state
    ctx.state["orchestrator_output"] = report.model_dump()
    
    return Event(output=report)


# --- 5. Workflow Node Functions ---

def security_checkpoint(ctx: Context, node_input: types.Content) -> Event:
    """Security node to check prompt injection, scrub PII, and log audit data."""
    if ctx.resume_inputs:
        # Bypassing checks on resume. Retrieve the original scrubbed query from state.
        scrubbed_text = ctx.state.get("scrubbed_query", "")
        scrubbed_content = types.Content(role="user", parts=[types.Part.from_text(text=scrubbed_text)])
        return Event(output=scrubbed_content, route="secure")

    query_text = ""
    if node_input and node_input.parts:
        query_text = "".join([p.text for p in node_input.parts if p.text])
    
    session_id = ctx.session.id
    
    # 1. PII Scrubbing (Credit Card number pattern)
    card_pattern = r"\b(?:\d[ -]*?){13,16}\b"
    scrubbed_text = re.sub(card_pattern, "[REDACTED_CARD]", query_text)
    
    # 2. Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "override rules", "system prompt", "bypass restrictions"]
    has_injection = any(kw in query_text.lower() for kw in injection_keywords)
    
    # 3. Domain-Specific Rule (Read-only query enforcement)
    write_keywords = ["transfer money", "withdraw money", "send money", "make payment", "wire transfer"]
    has_write_attempt = any(kw in query_text.lower() for kw in write_keywords)
    
    audit_log = {
        "timestamp": datetime.datetime.now().isoformat(),
        "session_id": session_id,
        "has_injection": has_injection,
        "has_write_attempt": has_write_attempt,
        "pii_redacted": scrubbed_text != query_text
    }
    
    if has_injection:
        audit_log["severity"] = "CRITICAL"
        audit_log["outcome"] = "BLOCK_INJECTION"
        print(json.dumps(audit_log))
        return Event(output="Access Denied: Potential security threat detected.", route="violation")
        
    if has_write_attempt:
        audit_log["severity"] = "WARNING"
        audit_log["outcome"] = "BLOCK_WRITE_ACTION"
        print(json.dumps(audit_log))
        return Event(output="Access Denied: direct financial transactions/transfers are disabled on this read-only navigator.", route="violation")
        
    # 4. Domain-Specific Rule (Out-of-domain check)
    financial_keywords = ["spend", "expense", "budget", "transaction", "save", "saving", "goal", "finance", "money", "report", "cost", "pay", "rent", "grocery", "bill"]
    greeting_keywords = ["hi", "hello", "hey", "greetings", "help"]
    is_financial = any(kw in query_text.lower() for kw in financial_keywords) or any(kw in query_text.lower() for kw in greeting_keywords)
    
    if not is_financial and query_text.strip():
        audit_log["severity"] = "WARNING"
        audit_log["outcome"] = "BLOCK_OUT_OF_DOMAIN"
        print(json.dumps(audit_log))
        return Event(output="Access Denied: I can only assist with personal finance, expense categorization, and savings inquiries.", route="violation")

    audit_log["severity"] = "INFO"
    audit_log["outcome"] = "PASS"
    print(json.dumps(audit_log))
    
    # Save the scrubbed query into state
    ctx.state["scrubbed_query"] = scrubbed_text
    
    # Pass clean input downstream to the orchestrator
    scrubbed_content = types.Content(role="user", parts=[types.Part.from_text(text=scrubbed_text)])
    return Event(output=scrubbed_content, route="secure")

def decision_node(ctx: Context, node_input: Any) -> Event:
    """Decision node to route based on whether human-in-the-loop review is required."""
    # Convert dict to OrchestratorReport if necessary
    if isinstance(node_input, dict):
        report = OrchestratorReport(**node_input)
    else:
        report = node_input
        
    if getattr(report, "needs_human_approval", False):
        return Event(output=report, route="needs_approval")
    return Event(output=report, route="auto_approved")

async def human_approval(ctx: Context, node_input: Any):
    """HITL approval gate using RequestInput."""
    if isinstance(node_input, dict):
        report = OrchestratorReport(**node_input)
    else:
        report = node_input

    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="approve_budget",
            message="⚠️ Large expense or high spending detected in your report. Do you approve this financial plan? (Reply 'yes' or 'no')"
        )
        return
    
    user_response = ctx.resume_inputs.get("approve_budget", "no").strip().lower()
    ctx.state["human_approval_response"] = user_response
    
    if user_response == "yes":
        report.summary += "\n\n**[Status: APPROVED BY USER]**"
    else:
        report.summary += "\n\n**[Status: REJECTED BY USER]**"
        
    yield Event(output=report)

def security_violation(node_input: str) -> str:
    """Handles security violation state and passes error output."""
    return node_input

def finalize_output(ctx: Context, node_input: Any):
    """Formats and prints the final report output for UI rendering."""
    # Convert dict to OrchestratorReport if necessary
    if isinstance(node_input, dict):
        report = OrchestratorReport(**node_input)
    elif isinstance(node_input, OrchestratorReport):
        report = node_input
    else:
        report = None

    if report is not None:
        approval = ctx.state.get("human_approval_response", "Auto-Approved").upper()
        summary = f"### 📊 Finance Navigator Report\n\n**Review Status:** {approval}\n\n{report.summary}"
        
        summary += "\n\n#### 🏷️ Expense Categorization"
        categorization = report.categorization
        if isinstance(categorization, dict):
            categorized_transactions = categorization.get("categorized_transactions", [])
            total_spent = categorization.get("total_spent", 0.0)
            budget_alerts = categorization.get("budget_alerts", [])
        else:
            categorized_transactions = getattr(categorization, "categorized_transactions", [])
            total_spent = getattr(categorization, "total_spent", 0.0)
            budget_alerts = getattr(categorization, "budget_alerts", [])
            
        for tx in categorized_transactions:
            if isinstance(tx, dict):
                tx_desc = tx.get("description", "")
                tx_amt = tx.get("amount", 0.0)
                tx_cat = tx.get("category", "")
            else:
                tx_desc = getattr(tx, "description", "")
                tx_amt = getattr(tx, "amount", 0.0)
                tx_cat = getattr(tx, "category", "")
            summary += f"\n- **{tx_desc}**: ${tx_amt:.2f} ({tx_cat})"
            
        summary += f"\n\n**Total Spent:** ${total_spent:.2f}"
        
        if budget_alerts:
            summary += "\n\n⚠️ **Budget Alerts:**"
            for alert in budget_alerts:
                summary += f"\n- {alert}"
                
        savings = report.savings
        if isinstance(savings, dict):
            savings_goal = savings.get("savings_goal", 0.0)
            estimated_savings = savings.get("estimated_savings", 0.0)
            suggestions = savings.get("suggestions", [])
        else:
            savings_goal = getattr(savings, "savings_goal", 0.0)
            estimated_savings = getattr(savings, "estimated_savings", 0.0)
            suggestions = getattr(savings, "suggestions", [])
            
        summary += "\n\n#### 💡 Savings Recommendations"
        summary += f"\n- **Savings Goal:** ${savings_goal:.2f}"
        summary += f"\n- **Estimated Savings:** ${estimated_savings:.2f}"
        for tip in suggestions:
            summary += f"\n- {tip}"
    else:
        summary = f"### 🔒 Security Alert\n\n{str(node_input)}"
        
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=summary)]))
    yield Event(output=summary)


# --- 6. Workflow Graph Assembly ---

workflow = Workflow(
    name="finance_navigator_workflow",
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {
            "secure": orchestrator_node,
            "violation": security_violation
        }),
        (orchestrator_node, decision_node),
        (decision_node, {
            "needs_approval": human_approval,
            "auto_approved": finalize_output
        }),
        (human_approval, finalize_output),
        (security_violation, finalize_output)
    ],
    rerun_on_resume=True
)

app = App(
    root_agent=workflow,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)
