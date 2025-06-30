import tempfile
from lightrag.user_profile import (
    save_user_profile,
    load_user_profile,
    update_user_profile,
    revert_user_profile,
    auto_tag_entities,
    record_branch_feedback,
    analyze_behavior,
    append_conversation_history,
    record_query_usage,
)


def test_profile_version_and_tags(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("USER_PROFILE_DIR", tmpdir)
        user_id = "test_user"
        save_user_profile(user_id, {"preferences": {"lang": "fr"}})
        update_user_profile(user_id, {"preferences": {"format": "md"}})
        profile = load_user_profile(user_id)
        assert profile["_version"] == 1
        update_user_profile(user_id, {"context": {"org": "ANSE"}})
        profile = load_user_profile(user_id)
        assert profile["_version"] == 2
        assert profile["_history"][0]["version"] == 0
        revert_user_profile(user_id, 1)
        profile = load_user_profile(user_id)
        assert profile["_version"] == 1
        auto_tag_entities(user_id, ["foo", "bar", "foo"])
        profile = load_user_profile(user_id)
        assert profile["tagged_entities"]["foo"] == 2
        record_branch_feedback(user_id, ["A", "B"], "positive")
        assert len(load_user_profile(user_id)["branch_feedback"]) == 1
        append_conversation_history(
            user_id, "c1", [{"role": "user", "content": "hello world"}]
        )
        record_query_usage(user_id, "hello world")
        record_query_usage(user_id, "hello world")
        analysis = analyze_behavior(user_id)
        assert analysis["negative_feedback"] >= 0
        assert analysis["top_queries"][0][0] == "hello world"
