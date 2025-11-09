"""
Conversation memory management.
Used to store and manage the conversation history between the Agent and the user.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any


class ConversationMemory:
    """Manage memory for conversation sessions."""

    def __init__(self, storage_dir: str = "./.data/conversations"):
        """Initialize the conversation memory.

        Args:
            storage_dir: Directory to store conversations (one JSON file per session).
        """
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
        self.sessions: dict[str, dict[str, Any]] = {}
        self._load_all_sessions()

    def _ensure_storage_dir(self):
        """Ensure the storage directory exists."""
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_session_file_path(self, session_id: str) -> str:
        """Get the file path for a session."""
        return os.path.join(self.storage_dir, f"{session_id}.json")

    def _load_all_sessions(self):
        """Load all sessions (only metadata; not the full content)."""
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.endswith(".json"):
                    session_id = filename[:-5]  # remove .json
                    file_path = os.path.join(self.storage_dir, filename)
                    try:
                        with open(file_path, encoding="utf-8") as f:
                            session_data = json.load(f)
                            self.sessions[session_id] = session_data
                    except Exception as e:
                        print(f"Warning: Failed to load session {session_id}: {e}")
        except Exception as e:
            print(f"Warning: Failed to list sessions: {e}")

    def _load_session(self, session_id: str) -> dict[str, Any] | None:
        """Load a single session from file."""
        file_path = self._get_session_file_path(session_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load session {session_id}: {e}")
                return None
        return None

    def _save_session(self, session_id: str):
        """Persist a single session to its dedicated JSON file."""
        if session_id not in self.sessions:
            return

        file_path = self._get_session_file_path(session_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.sessions[session_id], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error: Failed to save session {session_id}: {e}")

    def create_session(self) -> str:
        """Create a new conversation session.

        Returns:
            session_id: ID of the new session.
        """
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        self.sessions[session_id] = {
            "session_id": session_id,
            "created_at": now,
            "updated_at": now,
            "messages": [],
            "criteria": {
                "city": None,
                "max_price": None,
                "min_size": None,
                "commute_target": None,
            },
            "status": "collecting",  # collecting, ready, searching, completed
            "search_results": None,
        }

        self._save_session(session_id)
        return session_id

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session data.

        Args:
            session_id: Session ID.

        Returns:
            The session data, or None if not found.
        """
        return self.sessions.get(session_id)

    def add_message(
        self, session_id: str, role: str, content: str, metadata: dict | None = None
    ):
        """Append a message to the session.

        Args:
            session_id: Session ID.
            role: Role of the message (user/assistant/system).
            content: Message content.
            metadata: Optional extra metadata.
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }

        self.sessions[session_id]["messages"].append(message)
        self.sessions[session_id]["updated_at"] = datetime.now(UTC).isoformat()
        self._save_session(session_id)

    def update_criteria(self, session_id: str, criteria_updates: dict[str, Any]):
        """Update the session's search criteria.

        Args:
            session_id: Session ID.
            criteria_updates: The criteria to update.
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        self.sessions[session_id]["criteria"].update(criteria_updates)
        self.sessions[session_id]["updated_at"] = datetime.now(UTC).isoformat()

        # Check whether all criteria have been collected
        criteria = self.sessions[session_id]["criteria"]
        if all(criteria.values()):
            self.sessions[session_id]["status"] = "ready"

        self._save_session(session_id)

    def update_status(self, session_id: str, status: str):
        """Update the session status.

        Args:
            session_id: Session ID.
            status: New status (collecting/ready/searching/completed).
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        self.sessions[session_id]["status"] = status
        self.sessions[session_id]["updated_at"] = datetime.now(UTC).isoformat()
        self._save_session(session_id)

    def save_search_results(self, session_id: str, results: list[dict]):
        """Store search results in the session.

        Args:
            session_id: Session ID.
            results: List of search results.
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")

        self.sessions[session_id]["search_results"] = results
        self.sessions[session_id]["status"] = "completed"
        self.sessions[session_id]["updated_at"] = datetime.now(UTC).isoformat()
        self._save_session(session_id)

    def get_messages(self, session_id: str, limit: int | None = None) -> list[dict]:
        """Get the message history for a session.

        Args:
            session_id: Session ID.
            limit: Optional maximum number of most recent messages to return.

        Returns:
            List of message dicts.
        """
        if session_id not in self.sessions:
            return []

        messages = self.sessions[session_id]["messages"]
        if limit:
            return messages[-limit:]
        return messages

    def get_criteria(self, session_id: str) -> dict[str, Any]:
        """Get the search criteria for a session.

        Args:
            session_id: Session ID.

        Returns:
            Criteria dictionary.
        """
        if session_id not in self.sessions:
            return {}
        return self.sessions[session_id]["criteria"]

    def is_ready_to_search(self, session_id: str) -> bool:
        """Check whether the session is ready to perform a search.

        Args:
            session_id: Session ID.

        Returns:
            True if ready, else False.
        """
        if session_id not in self.sessions:
            return False

        criteria = self.sessions[session_id]["criteria"]
        return all(criteria.values())

    def list_sessions(self, limit: int = 5) -> list[dict[str, Any]]:
        """List all sessions (most recent first).

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of session dicts.
        """
        sessions = sorted(
            self.sessions.values(), key=lambda x: x["updated_at"], reverse=True
        )
        return sessions[:limit]

    def delete_session(self, session_id: str):
        """Delete a session and its persisted file.

        Args:
            session_id: Session ID.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            # Delete file
            file_path = self._get_session_file_path(session_id)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error: Failed to delete session file {session_id}: {e}")

    def format_conversation_history(
        self, session_id: str, limit: int | None = None
    ) -> str:
        """Format conversation history as plain text.

        Args:
            session_id: Session ID.
            limit: Optional max number of recent messages.

        Returns:
            A single string with one line per message.
        """
        messages = self.get_messages(session_id, limit)

        formatted = []
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            formatted.append(f"{role}: {content}")

        return "\n".join(formatted)
