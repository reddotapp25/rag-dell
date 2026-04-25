"""LangGraph pipeline: planner -> specialist agents -> synthesizer."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from .llm import get_llm
from .tools import (
    duckduckgo_search,
    general_rag_tool,
    policy_clause_extract,
    policy_rag_tool,
    product_rag_tool,
    tech_rag_tool,
)

logger = logging.getLogger("app.graph")


def _user_safe_error(exc: Exception) -> str:
    """Return a short, non-leaky error message for the UI.

    Raw upstream exceptions from the LLM provider can include organization
    IDs, service-tier metadata, billing URLs, and occasionally request
    headers. We log the full detail server-side and surface a classified
    short message to the client.
    """
    text = str(exc).lower()
    if "rate_limit" in text or "rate limit" in text or "429" in text:
        return (
            "The language model provider is currently rate-limiting requests. "
            "Please try again in a few minutes."
        )
    if "invalid_api_key" in text or "authentication" in text or "401" in text:
        return "The language model provider rejected the request credentials."
    if "timeout" in text or "timed out" in text:
        return "The language model provider timed out. Please try again."
    if "connection" in text or "network" in text:
        return "Could not reach the language model provider. Please try again."
    return "The language model provider returned an unexpected error."

VALID_AGENTS = ["product_agent", "policy_agent", "tech_agent", "general_agent"]

AGENT_LABELS = {
    "product_agent": "Product Agent",
    "policy_agent": "Policy Agent",
    "tech_agent": "Tech Agent",
    "general_agent": "General Agent",
}


class AgentState(TypedDict, total=False):
    query: str
    response: str
    selected_agents: List[str]
    agent_outputs: Dict[str, str]
    debug_log: str


@lru_cache(maxsize=1)
def _build_agents():
    llm = get_llm()
    product = create_react_agent(
        llm,
        tools=[product_rag_tool, duckduckgo_search],
        prompt=(
            "You are the Product Agent. Handle buying questions, product specs, "
            "inventory, and prices. Prefer internal RAG search for company facts. "
            "Use DuckDuckGo only when the user asks for current or external info. "
            "Be concise and practical."
        ),
    )
    policy = create_react_agent(
        llm,
        tools=[policy_rag_tool, policy_clause_extract, duckduckgo_search],
        prompt=(
            "You are the Policy Agent. Handle return rules, warranty, shipping, "
            "and FAQ. Prefer internal RAG search for company policy. "
            "Use DuckDuckGo only if current external info is required. "
            "If the policy is not found internally, say so clearly.\n\n"
            "IMPORTANT: After you have an answer, you MUST call the "
            "`policy_clause_extract` tool with the user's question to pull the "
            "EXACT verbatim clause from the policy documents. Then end your "
            "response with an 'Evidence' section that shows that clause "
            "unchanged (as a block quote) together with its source file, so "
            "the user can see proof that the answer is correct. If the tool "
            "returns NO_CLAUSE_FOUND, say explicitly that no matching clause "
            "was found in the internal policy documents and do not fabricate "
            "one."
        ),
    )
    tech = create_react_agent(
        llm,
        tools=[tech_rag_tool, duckduckgo_search],
        prompt=(
            "You are the Tech Agent. Handle troubleshooting and technical "
            "explanations. Use internal technical documents first. "
            "Use DuckDuckGo when updated troubleshooting or external facts are "
            "needed. Give safe, step-by-step advice."
        ),
    )
    general = create_react_agent(
        llm,
        tools=[general_rag_tool, duckduckgo_search],
        prompt=(
            "You are the General Agent. Handle general chat, broad questions, "
            "and off-topic requests. Use DuckDuckGo when outside or current "
            "information is needed. Be helpful and clear."
        ),
    )
    return {
        "product_agent": product,
        "policy_agent": policy,
        "tech_agent": tech,
        "general_agent": general,
    }


def _normalize_agent_list(text: str) -> List[str]:
    cleaned = text.lower().replace('"', "").replace("'", "")
    raw = [p.strip() for p in cleaned.replace("\n", ",").split(",") if p.strip()]
    agents: List[str] = []
    for item in raw:
        if item in VALID_AGENTS and item not in agents:
            agents.append(item)
    return agents or ["general_agent"]


PLANNER_PROMPT = """
You are a planner for a collaborative multi-agent AI system.

Choose one or more agents that should help answer the user's question.

Available agents:
- product_agent = products, catalog, specs, prices, inventory, buying decisions
- policy_agent = return policy, warranty, refund, shipping, FAQ, store rules
- tech_agent = troubleshooting, repair, setup, bugs, device support, technical issues
- general_agent = general explanation, broad knowledge, synthesis help, anything else

Rules:
1. You may choose MULTIPLE agents if the question spans multiple domains.
2. Return a comma-separated list using only these exact names.
3. Do not explain your choice.
4. If unsure, include general_agent.

Examples:
- "What products are available?" -> product_agent
- "What is your return policy and warranty?" -> policy_agent
- "What Dell laptops do you have and can I return them after 14 days?" -> product_agent, policy_agent
- "What products are available, what is the return policy, and how do I fix overheating?" -> product_agent, policy_agent, tech_agent
- "Tell me the latest AI trends in 2026" -> general_agent
""".strip()


def planner_node(state: AgentState) -> AgentState:
    query = state["query"]
    try:
        resp = get_llm().invoke(
            [SystemMessage(content=PLANNER_PROMPT), HumanMessage(content=query)]
        )
        selected = _normalize_agent_list(resp.content)
    except Exception:
        selected = ["general_agent"]
    return {
        "selected_agents": selected,
        "debug_log": f"Planner selected: {', '.join(selected)}",
    }


def _extract_final_text(result) -> str:
    try:
        msgs = result.get("messages", [])
        if msgs:
            last = msgs[-1]
            return getattr(last, "content", str(last))
    except Exception:
        pass
    return str(result)


def run_selected_agents_node(state: AgentState) -> AgentState:
    agents = _build_agents()
    query = state["query"]
    selected = state.get("selected_agents") or ["general_agent"]
    outputs: Dict[str, str] = {}
    logs = [state.get("debug_log", "")]

    for name in selected:
        agent = agents.get(name)
        if agent is None:
            outputs[name] = f"Unknown agent: {name}"
            continue
        try:
            result = agent.invoke({"messages": [HumanMessage(content=query)]})
            outputs[name] = _extract_final_text(result)
        except Exception as e:
            logger.exception("Agent %s failed", name)
            outputs[name] = _user_safe_error(e)
        logs.append(f"{AGENT_LABELS.get(name, name)} contributed.")

    return {
        "agent_outputs": outputs,
        "debug_log": "\n".join([x for x in logs if x]),
    }


def synthesize_node(state: AgentState) -> AgentState:
    query = state["query"]
    outputs = state.get("agent_outputs", {}) or {}
    selected = state.get("selected_agents", []) or []

    if not outputs:
        return {
            "response": "No specialist output was produced.",
            "debug_log": (state.get("debug_log", "") or "")
            + "\nNo agent outputs to synthesize.",
        }

    notes = [f"[{n}]\n{outputs[n]}" for n in selected if n in outputs]

    prompt = f"""
You are the final synthesizer in a multi-agent system.

User question:
{query}

Specialist outputs:
{chr(10).join(notes)}

Instructions:
1. Merge the specialist outputs into one coherent final answer.
2. Keep the response concise but complete.
3. If different agents cover different parts, integrate them smoothly.
4. If something is uncertain or missing, say so clearly.
5. Do not mention internal chain-of-thought.
6. When helpful, organize the answer with short sections or bullets.
7. If any specialist included an "Evidence" section with a block-quoted
   verbatim clause and its source, preserve that block quote EXACTLY as
   written (do not paraphrase, shorten, or reformat it) and keep it under a
   final "Evidence" heading so the user can see proof of the answer.
""".strip()

    try:
        resp = get_llm().invoke(
            [
                SystemMessage(content="You are a careful answer synthesizer."),
                HumanMessage(content=prompt),
            ]
        )
        final = resp.content.strip()
    except Exception as e:
        logger.exception("Synthesizer failed")
        final = (
            f"{_user_safe_error(e)}\n\n"
            "Falling back to raw specialist outputs:\n\n"
            + "\n\n".join(notes)
        )

    return {
        "response": final,
        "debug_log": (state.get("debug_log", "") or "")
        + f"\nSynthesizer merged outputs from: {', '.join(selected)}",
    }


@lru_cache(maxsize=1)
def get_app():
    workflow = StateGraph(AgentState)
    workflow.add_node("planner", planner_node)
    workflow.add_node("run_selected_agents", run_selected_agents_node)
    workflow.add_node("synthesize", synthesize_node)
    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "run_selected_agents")
    workflow.add_edge("run_selected_agents", "synthesize")
    workflow.add_edge("synthesize", END)
    return workflow.compile()


def run_query(query: str) -> Dict:
    app = get_app()
    result = app.invoke(
        {
            "query": query,
            "response": "",
            "selected_agents": [],
            "agent_outputs": {},
            "debug_log": "",
        }
    )
    return {
        "query": query,
        "response": result.get("response", ""),
        "selected_agents": result.get("selected_agents", []),
        "agent_outputs": result.get("agent_outputs", {}),
        "debug_log": result.get("debug_log", ""),
    }
