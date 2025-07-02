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
    """Update an existing user profile with new information and create a version."""
    profile = load_user_profile(user_id)
    version = profile.get("_version", 0) + 1
    history = profile.setdefault("_history", [])
    if profile:
        prev = profile.copy()
        prev.pop("_history", None)
        history.append(
            {
                "version": version - 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "profile": prev,
            }
        )
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(profile.get(key), dict):
            profile[key].update(value)
        else:
            profile[key] = value
    profile["_version"] = version
    save_user_profile(user_id, profile)
    return profile


def personalize_query(raw_query: str, user_profile: Dict[str, Any]) -> str:
    """Modify query text according to user profile preferences."""
    context = user_profile.get("context", {})
    if context.get("mission") == "analyse sécuritaire":
        raw_query += " dans le contexte sécuritaire du Mali"
    return raw_query


def profile_to_prompt(user_profile: Dict[str, Any]) -> str:
    """Convert a user profile into a natural language prompt snippet."""
    parts: list[str] = []
    prefs = user_profile.get("preferences", {})
    if (lang := prefs.get("lang")):
        parts.append(f"Réponds en {lang}.")
    if (fmt := prefs.get("format")):
        parts.append(f"Utilise le format {fmt}.")
    if (detail := prefs.get("detail_level")):
        parts.append(f"Niveau de détail : {detail}.")
    context = user_profile.get("context", {})
    if (org := context.get("organization")):
        parts.append(f"Organisation : {org}.")
    if (mission := context.get("mission")):
        parts.append(f"Mission : {mission}.")
    return " ".join(parts)


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


def record_query_usage(user_id: str, query: str) -> None:
    """Record a query in the user's usage history for implicit feedback."""
    profile = load_user_profile(user_id)
    usage = profile.setdefault("query_usage", {})
    usage[query] = usage.get(query, 0) + 1
    profile["query_usage"] = usage
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


def revert_user_profile(user_id: str, version: int) -> Dict[str, Any]:
    """Revert profile to a specific version from history."""
    profile = load_user_profile(user_id)
    history = profile.get("_history", [])
    for item in reversed(history):
        if item.get("version") == version:
            profile = item["profile"]
            profile["_version"] = version
            save_user_profile(user_id, profile)
            return profile
    raise ValueError("Version not found")


def record_branch_feedback(
    user_id: str,
    branch: List[str],
    rating: Literal["positive", "negative"],
    notes: Optional[str] = None,
) -> None:
    """Store feedback for a specific Tree of Thought branch."""
    profile = load_user_profile(user_id)
    entries = profile.setdefault("branch_feedback", [])
    entries.append(
        {
            "branch": branch,
            "rating": rating,
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_user_profile(user_id, profile)


def auto_tag_entities(user_id: str, entities: List[str]) -> None:
    """Automatically tag corrected entities with frequency counters."""
    profile = load_user_profile(user_id)
    tags = profile.setdefault("tagged_entities", {})
    for ent in entities:
        tags[ent] = tags.get(ent, 0) + 1
    profile["tagged_entities"] = tags
    save_user_profile(user_id, profile)


def analyze_behavior(user_id: str) -> Dict[str, Any]:
    """Return simple behavioural metrics extracted from the profile."""
    profile = load_user_profile(user_id)
    word_counts: Dict[str, int] = {}
    for conv in profile.get("conversations", {}).values():
        for msg in conv:
            if msg.get("role") == "user":
                for word in msg.get("content", "").split():
                    word_counts[word] = word_counts.get(word, 0) + 1
    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    errors = sum(
        1 for fb in profile.get("feedback", []) if fb.get("rating") == "negative"
    )
    top_queries = sorted(
        profile.get("query_usage", {}).items(), key=lambda x: x[1], reverse=True
    )[:5]
    return {
        "top_words": top_words,
        "negative_feedback": errors,
        "top_queries": top_queries,
    }
