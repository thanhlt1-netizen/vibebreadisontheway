from textutil import sanitize, detect_lang, split_for_translation
from chunker import chunk_text

def test_sanitize():
    assert "[cười]" in sanitize("Anh ta [cười] rồi đi.")
    s = sanitize("[Level up!] Bạn đã lên cấp  [Ghi chú dịch giả]")
    assert "[" not in s and "Level up!" in s and "  " not in s

def test_lang():
    assert detect_lang("这是一个很长的中文句子，用来测试语言检测功能是否正常。") == "zh"
    assert detect_lang("これはテストです。ひらがなとカタカナ。") == "ja"
    assert detect_lang("안녕하세요 이것은 테스트입니다") == "ko"
    assert detect_lang("Anh ấy đã đi về nhà từ rất sớm.") == "vi"
    assert detect_lang("He went home very early in the morning.") == "en"

def test_split_translation():
    t = "\n".join(["đoạn " * 100] * 20)
    bs = split_for_translation(t, 3000)
    assert all(len(b) <= 3000 for b in bs) and "\n".join(bs) == t

def test_chunks_min50():
    cs = chunk_text("Ừ.\nVâng.\nĐược rồi, chúng ta đi thôi nào các bạn ơi, trời sắp tối rồi.\nXong.")
    assert all(len(c) >= 50 for c in cs[:-1]) or len(cs) == 1

def test_first_chunk_short():
    cs = chunk_text(" ".join(["Đây là một câu khá dài để thử đoạn đầu tiên."] * 12))
    assert len(cs[0]) <= 170 and len(cs) > 2
