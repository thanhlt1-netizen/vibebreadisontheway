"""Tải model VieNeu vào ./hf_cache để đóng gói sẵn trong bộ cài (người dùng khỏi phải tải lần đầu)."""
import os
os.environ["HF_HOME"] = os.path.abspath("hf_cache")
import config
from vieneu import Vieneu
tts = Vieneu()
tts.infer("Xin chào các bạn, đây là bản thử giọng.", voice=config.DEFAULT_VOICE)
print("OK — model đã nằm trong", os.environ["HF_HOME"])
