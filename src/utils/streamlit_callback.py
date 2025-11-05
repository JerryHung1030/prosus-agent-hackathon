# FILE: ./src/utils/streamlit_callback.py
# (FIXED Version)

import streamlit as st
from langchain_core.callbacks import BaseCallbackHandler


# We only need this class.
class StreamlitCallbackHandler(BaseCallbackHandler):
    """
    A callback handler that renders the agent's thought process
    in a structured, chat-like interface in Streamlit.
    """

    def __init__(self, container):
        super().__init__()
        self.container = container
        self.agent_icons = {"researcher_agent": "🔬", "writer_agent": "✍️", "Agent": "🤖"}

    def get_agent_name(self, kwargs):
        """Helper to get agent name from kwargs, default to 'Agent'"""
        return kwargs.get("agent_name", "Agent")

    def on_agent_action(self, action, **kwargs):
        """Called when an agent is about to perform an action."""
        agent_name = self.get_agent_name(kwargs)
        icon = self.agent_icons.get(agent_name, "🤖")

        # Display the "Thought" process
        with self.container.chat_message(name=agent_name, avatar=icon):
            st.markdown(f"🧠 **Thinking...**\n\n{kwargs.get('thought', 'Thinking...')}")

        # Display the "Action"
        with self.container.chat_message(name=agent_name, avatar=icon):
            st.markdown(
                f"🛠️ **Action:** `{action.tool}`\n\n**Input:**\n```\n{action.tool_input}\n```"
            )

    def on_tool_end(self, output, **kwargs):
        """Called when a tool finishes running."""
        # Display the "Observation"
        with self.container.chat_message(name="System", avatar="📡"):
            st.markdown(f"**Observation (Output):**\n```\n{output}\n```")

    def on_agent_finish(self, finish, **kwargs):
        """Called when an agent finishes its work."""
        agent_name = self.get_agent_name(kwargs)
        icon = self.agent_icons.get(agent_name, "🤖")

        with self.container.chat_message(name=agent_name, avatar=icon):
            st.markdown(f"🏁 **Finished Task**\n\n{finish.return_values.get('output', 'N/A')}")


def create_step_callback(handler: StreamlitCallbackHandler, agent_name: str):
    """
    Create a callable compatible with CrewAI Agent.step_callback.

    This adapter renders common step payload fields in the Streamlit log container
    and falls back to printing raw args/kwargs when unknown.
    """

    def _step_callback(*args, **kwargs):  # noqa: ANN001
        icon = handler.agent_icons.get(agent_name, "🤖")
        with handler.container.chat_message(name=agent_name, avatar=icon):
            payload = None
            if args and isinstance(args[0], dict):
                payload = args[0]
            elif kwargs:
                payload = kwargs

            if isinstance(payload, dict):
                thought = payload.get("thought") or payload.get("thoughts")
                action = payload.get("action") or payload.get("tool")
                tool_input = payload.get("tool_input") or payload.get("input")
                observation = payload.get("observation") or payload.get("output")

                blocks = []
                if thought:
                    blocks.append(f"🧠 **Thinking**\n\n{thought}")
                if action:
                    blocks.append(f"🛠️ **Action:** `{action}`")
                if tool_input:
                    blocks.append(f"**Input:**\n```\n{tool_input}\n```")
                if observation:
                    blocks.append(f"**Observation:**\n```\n{observation}\n```")

                if blocks:
                    st.markdown("\n\n".join(blocks))
                    return

            # Fallback: raw dump
            st.markdown(f"**Step:**\n```\nargs={args}\nkwargs={kwargs}\n```")

    return _step_callback
