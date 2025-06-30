import os
import json
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timezone

PROFILE_DIR = os.getenv("USER_PROFILE_DIR", "user_profiles")


def load_user_profile(user_id: str) -> Dict[str, Any]:
    """Load user profile from disk.

    Parameters
    ----------
    user_id : str
        Unique identifier of the user.

    Returns
    -------
    dict
        Profile data if available, otherwise empty dict.
    """
    os.makedirs(PROFILE_DIR, exist_ok=True)
    profile_path = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_user_profile(user_id: str, profile: Dict[str, Any]) -> None:
    """Persist user profile to disk."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    profile_path = os.path.join(PROFILE_DIR, f"{user_id}.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def update_user_profile(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing user profile with new information."""
    profile = load_user_profile(user_id)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(profile.get(key), dict):
            profile[key].update(value)
        else:
            profile[key] = value
    save_user_profile(user_id, profile)
    return profile


def personalize_query(raw_query: str, user_profile: Dict[str, Any]) -> str:
    """Modify query text according to user profile preferences."""
    context = user_profile.get("context", {})
    if context.get("mission") == "analyse sécuritaire":
        raw_query += " dans le contexte sécuritaire du Mali"
    return raw_query


def record_feedback(
    user_id: str,
    query: str,
    response: str,
    rating: Literal["positive", "negative"],
    notes: Optional[str] = None,
) -> None:
    """Record explicit user feedback for a given query and response."""
    profile = load_user_profile(user_id)
    feedback_list = profile.setdefault("feedback", [])
    feedback_list.append(
        {
            "query": query,
            "response": response,
            "rating": rating,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_user_profile(user_id, profile)


def get_conversation_history(
    user_id: str, conversation_id: str
) -> List[Dict[str, Any]]:
    """Return stored conversation history for a conversation of a user."""
    profile = load_user_profile(user_id)
    conversations = profile.get("conversations", {})
    return conversations.get(conversation_id, [])


def append_conversation_history(
    user_id: str,
    conversation_id: str,
    messages: List[Dict[str, str]],
    max_messages: int = 20,
) -> None:
    """Append new messages to a conversation history and persist it."""
    profile = load_user_profile(user_id)
    conversations = profile.setdefault("conversations", {})
    history = conversations.get(conversation_id, [])
    history.extend(messages)
    if len(history) > max_messages:
        history = history[-max_messages:]
    conversations[conversation_id] = history
    profile["conversations"] = conversations
    save_user_profile(user_id, profile)
