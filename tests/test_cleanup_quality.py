import pytest

import dictate.cleanup as cleanup_module
from dictate import config
from dictate.cleanup import cleanup

pytestmark = pytest.mark.skipif(
    not config.CLEANUP_MODEL_PATH.exists() or not config.LLAMACPP_SERVER_EXE.exists(),
    reason="cleanup model/llama-server binary not downloaded (run scripts/download_models.py)",
)


@pytest.fixture(scope="module")
def _real_cleanup_server():
    cleanup_module.preload()
    yield
    cleanup_module.shutdown()


# Real whisper output captured in dictate.log during a live voice test
# (2026-08-16 16:09:51). The original cleanup prompt silently deleted "You
# know the answer already, right? Anyway, like" and "I always makes those
# up." entirely from this exact input -- not just trimming filler, but
# dropping real content. This is the authoritative reproduction case.
_REAL_WHISPER_TRANSCRIPT_THAT_LOST_CONTENT = (
    "Okay, so I wanted to walk through the plan for next week. We've got a "
    "3 meeting scheduled, Monday at 9am, Wednesday afternoon and then "
    "Friday if we need it. I think the budget is around $12,000, but don't "
    "quote me on that. You know the answer already, right? Anyway, like "
    "the main thing is we need Sarah's sign up before we ship version 2.1. "
    "Can you send here the dog by end of day? Also, a quick question. Is "
    "the survey running on port 8,000 or 8,000 and 80? I always makes "
    "those up. One more thing. Remind me to email John at his Gmail "
    "address, not his workbar. Okay, I think that's it. Thank you."
)


def test_preserves_a_real_question_that_contains_words_also_used_as_filler(
    _real_cleanup_server,
):
    result = cleanup(_REAL_WHISPER_TRANSCRIPT_THAT_LOST_CONTENT)

    assert "you know the answer already" in result.lower()
    assert "right" in result.lower()


def test_preserves_a_meaningful_sentence_with_no_filler_words_at_all(
    _real_cleanup_server,
):
    result = cleanup(_REAL_WHISPER_TRANSCRIPT_THAT_LOST_CONTENT)

    assert "always" in result.lower()
    assert "those up" in result.lower()


def test_preserves_a_hedge_clause_expressing_real_uncertainty(_real_cleanup_server):
    raw = (
        "Um, so the invoice number is uh 4 4 7 2 B and it's due, I think, "
        "next Tuesday, or maybe Wednesday, not totally sure. Also remind "
        "me the wifi password is purple elephant 7 with a capital P."
    )

    result = cleanup(raw)

    assert "wednesday" in result.lower()
    assert "not totally sure" in result.lower()
