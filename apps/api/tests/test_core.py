import asyncio, pytest
from chunker import chunk_text
from fetcher import assert_public
from fastapi import HTTPException

def test_chunks_respect_limits():
    text = "\n".join(["Câu một khá ngắn. Câu hai cũng vậy! Còn đây là câu ba?"] * 30 + ["Ừ."])
    cs = chunk_text(text)
    assert all(50 <= len(c) <= 600 for c in cs), [len(c) for c in cs]
    assert "".join(cs).replace(" ", "").startswith("Câumộtkhángắn")

def test_long_sentence_split():
    cs = chunk_text("từ " * 400)
    assert all(len(c) <= 600 for c in cs) and len(cs) > 1

@pytest.mark.parametrize("u", ["http://127.0.0.1/x", "http://localhost/x", "file:///etc/passwd", "http://10.0.0.5/"])
def test_ssrf_blocked(u):
    with pytest.raises(HTTPException): asyncio.run(assert_public(u))
