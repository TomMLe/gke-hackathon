import asyncio
import os
import streamlit as st
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.memory import ConversationBufferMemory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from a2a.types import AgentCard
from cart_monitor_agent.agent import get_agent_card as cart_monitor_agent_card
from recommend_agent.agent import get_agent_card as recommend_agent_card
import httpx

# ============ LLM for ROUTING only ============
api_key = os.getenv("GOOGLE_API_KEY", "")
if not api_key:
    st.warning("GOOGLE_API_KEY is not set; routing LLM may fail.")
genai.configure(api_key=api_key)
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key)

# ============ Memory ============
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(return_messages=True)

# ============ Agent Cards ============
agent_cards = {
    "cart_monitor_agent": cart_monitor_agent_card(),
    "recommend_agent": recommend_agent_card(),
}

def format_agent_cards(cards):
    return "\n\n".join([
        f"Name: {label}\nDescription: {card.description}\nSkills:\n" +
        "\n".join([f"- {s.name}: {s.description}" for s in card.skills])
        for label, card in cards.items()
    ])

# ============ Router Prompt ============
router_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an intelligent router. Choose the most suitable agent for this request from the following:\n\n"
     "{agent_cards}\n\n"
     "Only return the agent name from this list: {agent_labels}"
     "Examples: User: Convert 10 USD to EUR → converter_agent ; "
     "User: What time is it in India? → converter_agent; "
     "User: Generate job description for a backend engineer → generator_agent; "
     "User: Write an email to a recruiter → generator_agent"),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{user_input}")
])

async def route(user_input: str) -> str:
    chain = router_prompt | llm | StrOutputParser()
    prompt_inputs = {
        "user_input": user_input,
        "chat_history": st.session_state.memory.load_memory_variables({}).get("chat_history", []),
        "agent_cards": format_agent_cards(agent_cards),
        "agent_labels": ", ".join(agent_cards.keys())
    }
    return (await chain.ainvoke(prompt_inputs)).strip()

# ============ A2A Delegation ============
# Endpoints: use K8s Service DNS
AGENT_ENDPOINTS = {
    "recommend_agent": os.getenv("RECOMMEND_A2A_URL", "http://recommend-agent:10103/a2a"),
    "cart_monitor_agent": os.getenv("CART_MONITOR_A2A_URL", "http://cart-monitor-agent:10102/a2a"),
}
# Optional bearer tokens
AGENT_TOKENS = {
    "recommend_agent": os.getenv("RECOMMEND_A2A_TOKEN", ""),
    "cart_monitor_agent": os.getenv("CART_MONITOR_A2A_TOKEN", ""),
}

def _memory_to_a2a_history(limit:int=10):
    """Map Streamlit memory to a simple A2A role/content list."""
    msgs = []
    history = st.session_state.memory.chat_memory.messages[-limit:]
    for m in history:
        # langchain stores roles as "human" or "ai"
        role = "user" if getattr(m, "type", "human") in ("human", "user") else "assistant"
        msgs.append({"role": role, "content": m.content})
    return msgs

async def delegate_to_peer(agent_label: str, user_input: str) -> str:
    url = AGENT_ENDPOINTS.get(agent_label)
    if not url:
        return f"❌ No endpoint configured for {agent_label}"

    headers = {"Content-Type": "application/json"}

    payload = {
        "messages": [
            # (optional) you can prepend a brief system cue here if desired
            # {"role": "system", "content": agent_cards[agent_label].description},
            *_memory_to_a2a_history(limit=10),
            {"role": "user", "content": user_input},
        ],
        "metadata": {"source": "host_orchestrator", "route": agent_label},
    }

    timeout = httpx.Timeout(30.0, read=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as e:
            return f"❌ Network error calling {agent_label}: {e!s}"

    if resp.status_code == 401:
        return f"❌ Unauthorized for {agent_label}: missing/invalid token"
    if resp.status_code == 403:
        return f"❌ Forbidden when calling {agent_label}"
    if resp.status_code >= 500:
        return f"❌ Peer error from {agent_label}: {resp.status_code}"

    try:
        data = resp.json()
    except ValueError:
        return f"❌ Invalid JSON from {agent_label}: {resp.text[:200]}"

    # Prefer 'output', fall back to last assistant message
    answer = data.get("output")
    if not answer:
        msgs = data.get("messages", [])
        if msgs:
            answer = msgs[-1].get("content")
    return answer or "⚠️ Peer returned no content."

# ============ Orchestrator main flow ============
async def process_input(user_input):
    # Save user message
    st.session_state.memory.save_context({"input": user_input}, {"output": "routing..."})

    # 1) Route to an agent
    agent_label = await route(user_input)
    agent_card = agent_cards.get(agent_label)

    if not agent_card:
        msg = f"❌ No agent found for label: {agent_label}"
        st.session_state.memory.save_context({"input": user_input}, {"output": msg})
        return msg

    # Display which agent was chosen
    st.write(f"📇 Agent Selected: {agent_label}")
    st.write(f"Description: {agent_card.description}")
    st.write("Skills:")
    for skill in agent_card.skills:
        st.write(f"- {skill.name}: {skill.description}")

    # 2) Delegate to peer via A2A
    answer = await delegate_to_peer(agent_label, user_input)

    # Save assistant turn
    st.session_state.memory.save_context({"input": user_input}, {"output": answer})
    return answer

# ============ Streamlit UI ============
st.title("ADK Agent Interface (Host Orchestrator)")

user_input = st.text_input("Your prompt:")

if st.button("Submit"):
    if user_input:
        with st.spinner("Processing..."):
            # Streamlit can be sync; run our async task safely
            try:
                result = asyncio.run(process_input(user_input))
            except RuntimeError:
                # If an event loop is already running (rare), fall back
                result = asyncio.get_event_loop().run_until_complete(process_input(user_input))
            st.write("🤖", result)
    else:
        st.warning("Please enter a prompt.")

# Display chat history
if st.session_state.memory.chat_memory.messages:
    st.subheader("Chat History")
    for msg in st.session_state.memory.chat_memory.messages:
        if msg.type == "human":
            st.write(f"User: {msg.content}")
        else:
            st.write(f"Agent: {msg.content}")
