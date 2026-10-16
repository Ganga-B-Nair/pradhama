"""Speech-to-text — owned by V. Runs as a CHILD PROCESS, not in-process.

docs/HACKATHON_PLAN.md §4, §6.3: this file is invoked via
`python -m app.agents.asr <audio_path> [model_size] [device]` so faster-whisper's
memory is fully released on exit, before Ollama loads for the LLM stages. Never
import this module into the main FastAPI process for inference — only the
worker's subprocess call should load the model.

Runs twice: task=transcribe (Malayalam original) and task=translate (English),
both with segment-level timestamps.
"""
import json
import sys


def _run_pass(model, audio_path: str, task: str) -> dict:
    segments, _ = model.transcribe(audio_path, task=task, language="ml", vad_filter=True)
    out_segments = []
    text_parts = []
    for index, seg in enumerate(segments):
        out_segments.append({"id": index, "start": seg.start, "end": seg.end, "text": seg.text.strip()})
        text_parts.append(seg.text.strip())
    return {"text": " ".join(text_parts), "segments": out_segments}


def transcribe_and_translate(audio_path: str, model_size: str = "small", device: str = "cpu") -> dict:
    """Returns {"malayalam": {"text": str, "segments": [...]}, "english": {"text": str, "segments": [...]}}."""
    from faster_whisper import WhisperModel

    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    malayalam = _run_pass(model, audio_path, task="transcribe")
    english = _run_pass(model, audio_path, task="translate")
    return {"malayalam": malayalam, "english": english}


if __name__ == "__main__":
    path = sys.argv[1]
    size = sys.argv[2] if len(sys.argv) > 2 else "small"
    dev = sys.argv[3] if len(sys.argv) > 3 else "cpu"
    result = transcribe_and_translate(path, size, dev)
    print(json.dumps(result))
