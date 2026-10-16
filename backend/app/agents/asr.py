"""Speech-to-text. Runs as a CHILD PROCESS, never imported into the API process.

docs/HACKATHON_PLAN.md §4, §6.3: invoked as
`python -m app.agents.asr <audio_path> [model_size] [device]` so faster-whisper's
memory is fully released when the process exits, before Ollama loads for the
LLM stages.

Runs twice with the language set to Malayalam: task=transcribe (the Malayalam
original) and task=translate (English), both with segment timestamps.
"""
import json
import sys


def _run_pass(model, audio_path: str, task: str) -> list[dict]:
    segments, _info = model.transcribe(audio_path, task=task, language="ml", vad_filter=True, beam_size=5)
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments if s.text.strip()]


def transcribe_and_translate(audio_path: str, model_size: str = "small", device: str = "cpu") -> dict:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type="float16" if device == "cuda" else "int8")
    return {
        "model": f"faster-whisper {model_size} ({device})",
        "malayalam": _run_pass(model, audio_path, "transcribe"),
        "english": _run_pass(model, audio_path, "translate"),
    }


if __name__ == "__main__":
    path = sys.argv[1]
    size = sys.argv[2] if len(sys.argv) > 2 else "small"
    dev = sys.argv[3] if len(sys.argv) > 3 else "cpu"
    sys.stdout.write(json.dumps(transcribe_and_translate(path, size, dev), ensure_ascii=False))
