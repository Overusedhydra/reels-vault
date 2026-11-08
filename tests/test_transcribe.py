"""Transcriber selection and settings (no models are loaded)."""

from __future__ import annotations

import sys
import types
import wave

from reels_vault import extract


def test_transcription_settings_prefers_arguments_then_config():
    cfg = {"whisper_model": "large-v3-turbo", "transcriber": "openai-whisper",
           "whisper_device": "cpu"}
    assert extract.transcription_settings(cfg) == ("large-v3-turbo", "openai-whisper", "cpu")
    assert extract.transcription_settings(cfg, "small", "faster-whisper", "cuda") == (
        "small", "faster-whisper", "cuda")
    assert extract.transcription_settings({}) == ("base", "auto", "auto")


def test_resolve_transcriber(monkeypatch):
    assert extract.resolve_transcriber("openai-whisper") == "openai-whisper"
    assert extract.resolve_transcriber("faster-whisper") == "faster-whisper"
    monkeypatch.setitem(sys.modules, "faster_whisper", types.ModuleType("faster_whisper"))
    assert extract.resolve_transcriber("auto") == "faster-whisper"
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import raises ImportError
    assert extract.resolve_transcriber("auto") == "openai-whisper"


def test_devices_fall_back_to_cpu(monkeypatch):
    monkeypatch.setattr(extract, "_cuda_available", lambda backend: False)
    assert extract._devices("faster-whisper", "auto") == ["cpu"]
    monkeypatch.setattr(extract, "_cuda_available", lambda backend: True)
    assert extract._devices("faster-whisper", "auto") == ["cuda", "cpu"]
    assert extract._devices("faster-whisper", "cpu") == ["cpu"]


def test_faster_whisper_falls_back_to_cpu_when_cuda_fails(monkeypatch, tmp_path):
    calls = []

    class Segment:
        start, end, text = 0.0, 1.0, " hola "

    class Info:
        language = "es"

    class FakeModel:
        def __init__(self, name, device, compute_type):
            calls.append((device, compute_type))
            self.device = device

        def transcribe(self, audio, beam_size=5):
            if self.device == "cuda":
                raise RuntimeError("Library libcublas.so.12 is not found")
            return iter([Segment()]), Info()

    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(extract, "_cuda_available", lambda backend: True)
    monkeypatch.setattr(extract, "_preload_cuda_libs", lambda: None)
    monkeypatch.setattr(extract, "_MODEL_CACHE", {})

    wav_path = tmp_path / "a.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 1600)

    result = extract.transcribe(str(wav_path), "tiny", "faster-whisper", "auto")
    assert calls == [("cuda", "float16"), ("cpu", "int8")]
    assert result["device"] == "cpu"
    assert result["language"] == "es"
    assert result["text"] == "hola"
    assert result["segments"][0]["text"] == "hola"
