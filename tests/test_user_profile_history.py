import tempfile
from lightrag.user_profile import (
    save_user_profile,
    append_conversation_history,
    get_conversation_history,
)


def test_append_and_get_history(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setenv("USER_PROFILE_DIR", tmpdir)
        user_id = "test_user"
        save_user_profile(user_id, {})
        append_conversation_history(
            user_id,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        )
        history = get_conversation_history(user_id)
        assert history == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        # append more than max_messages
        for i in range(25):
            append_conversation_history(
                user_id,
                [
                    {"role": "user", "content": str(i)},
                    {"role": "assistant", "content": str(i)},
                ],
            )
        history = get_conversation_history(user_id)
        assert len(history) <= 20
