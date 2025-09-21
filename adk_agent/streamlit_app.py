import asyncio
import streamlit as st
import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.memory import ConversationBufferMemory
from langgraph.prebuilt import create_react_agent
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from a2a.types import AgentCard
import os
from cart_monitor_agent.agent import get_agent_card as cart_monitor_agent_card
from recommend_agent.agent import get_agent_card as recommend_agent_card

# GOOGLE GEMINI API KEY
api_key = os.getenv("GOOGLE_API_KEY", "AIzaSyCv39vGzFZUHrida4TM9xV5RKN33zEVZ8A")
genai.configure(api_key=api_key)

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key)

# === Memory ===
if 'memory' not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(return_messages=True)

# MCP Toolset Configuration
mcp_host = os.getenv("MCP_SERVER_HOST", "ob-mcp-server")
mcp_port = int(os.getenv("MCP_SERVER_PORT", 8080))
mcp_path = os.getenv("MCP_SERVER_PATH", "/sse")
full_mcp_sse_url = f"http://{mcp_host}:{mcp_port}{mcp_path}"

connection_params = SseServerParams(
    url=full_mcp_sse_url,
    headers={'Accept': 'text/event-stream'}
)

tools = MCPToolset(connection_params=connection_params)

# Agent Cards
agent_cards = {
    "cart_monitor_agent": cart_monitor_agent_card(),
    "recommend_agent": recommend_agent_card()
}

# Router Prompt
router_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are an intelligent router. Choose the most suitable agent for this request from the following:\n\n"
               "{agent_cards}\n\n"
               "Only return the agent name from this list: {agent_labels}"
               "Examples: User: Convert 10 USD to EUR → converter_agent ; User: What time is it in India? → converter_agent; User: Generate job description for a backend engineer → generator_agent; User: Write an email to a recruiter → generator_agent"),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{user_input}")
])

def format_agent_cards(cards):
    return "\n\n".join([
        f"Name: {label}\nDescription: {card.description}\nSkills:\n" +
        "\n".join([f"- {s.name}: {s.description}" for s in card.skills])
        for label, card in cards.items()
    ])

async def route(user_input: str) -> str:
    chain = router_prompt | llm | StrOutputParser()
    prompt_inputs = {
        "user_input": user_input,
        "chat_history": st.session_state.memory.load_memory_variables({}).get("chat_history", []),
        "agent_cards": format_agent_cards(agent_cards),
        "agent_labels": ", ".join(agent_cards.keys())
    }
    return await chain.ainvoke(prompt_inputs)

async def process_input(user_input):
    st.session_state.memory.save_context({"input": user_input}, {"output": "routing..."})
    agent_label = (await route(user_input)).strip()

    agent_card = agent_cards.get(agent_label)
    if not agent_card:
        return f"❌ No agent found for label: {agent_label}"

    # Print selected AgentCard (in Streamlit)
    st.write(f"📇 AgentCard Selected: {agent_label}")
    st.write(f"Description: {agent_card.description}")
    st.write("Skills:")
    for skill in agent_card.skills:
        st.write(f"- {skill.name}: {skill.description}")

    selected_agent = create_react_agent(llm, tools)

    response = await selected_agent.ainvoke({
        "messages": [{"type": "human", "content": user_input}]
    })
    
    answer = response["messages"][-1].content
    st.session_state.memory.save_context({"input": user_input}, {"output": answer})
    return answer

# Streamlit UI
st.title("ADK Agent Interface")

user_input = st.text_input("Your prompt:")

if st.button("Submit"):
    if user_input:
        with st.spinner("Processing..."):
            result = asyncio.run(process_input(user_input))
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
