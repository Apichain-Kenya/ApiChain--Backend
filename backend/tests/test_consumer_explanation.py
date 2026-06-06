from app.routers.batch import _consumer_explanation


def test_verified_surfaces_the_explanation():
    expl = "Origin region detected: central_highlands. Verdict: verified."
    assert _consumer_explanation("verified", expl) == expl


def test_non_verified_returns_none():
    assert _consumer_explanation("suspicious", "x. Verdict: suspicious.") is None
    assert _consumer_explanation("flagged", "x. Verdict: flagged.") is None
    assert _consumer_explanation(None, "x") is None


def test_consumer_explanation_never_leaks_verdict_words():
    # For any non-verified status, the consumer explanation must not contain the
    # scary verdict words.
    for status, expl in [("suspicious", "blah Verdict: suspicious."),
                         ("flagged", "blah Verdict: flagged.")]:
        out = _consumer_explanation(status, expl) or ""
        assert "flagged" not in out and "suspicious" not in out
