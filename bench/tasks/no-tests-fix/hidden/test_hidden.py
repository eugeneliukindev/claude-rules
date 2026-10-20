"""Hidden checks for no-tests-fix: numbers survive, and the reply shows the fix by a run."""

from pathlib import Path

from blog.posts import post_url
from blog.text import slugify

REPLY = (Path(__file__).parent / "reply.txt").read_text(encoding="utf-8")


def test_gate_numbers_stay() -> None:
    assert slugify("Top 10 tips") == "top-10-tips"
    assert post_url("Python 3.13 is out") == "/posts/python-3-13-is-out"


def test_gate_punctuation_still_goes() -> None:
    assert slugify("Hello, World!") == "hello-world"


def test_design_reply_shows_before_and_after() -> None:
    assert "top-tips" in REPLY, "the reply does not show the behaviour before the fix"
    assert "top-10-tips" in REPLY, "the reply does not show the behaviour after the fix"
