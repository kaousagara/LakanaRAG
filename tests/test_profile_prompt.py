import tempfile
from lightrag.user_profile import profile_to_prompt


def test_profile_to_prompt_basic():
    profile = {
        "preferences": {"lang": "fr", "format": "markdown"},
        "context": {"organization": "ANSE", "mission": "analyse"},
    }
    prompt = profile_to_prompt(profile)
    assert "fr" in prompt
    assert "markdown" in prompt
    assert "ANSE" in prompt
