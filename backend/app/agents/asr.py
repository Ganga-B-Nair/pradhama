"""Speech-to-text — owned by V. Runs as a CHILD PROCESS, not in-process.

docs/HACKATHON_PLAN.md §4, §6.3: this file is invoked via
`python -m app.agents.asr <audio_path>` so faster-whisper's memory is fully
released on exit, before Ollama loads for the LLM stages. Never import this
module into the main FastAPI process for inference — only the worker's
subprocess call should load the model.

Runs twice: task=transcribe (Malayalam original) and task=translate (English),
both with segment-level timestamps.
"""
import json
import sys


def transcribe_and_translate(audio_path: str, model_size: str = "small") -> dict:
    """Returns {"malayalam": {"text": str, "segments": [...]}, "english": {"text": str, "segments": [...]}}."""
    raise NotImplementedError


if __name__ == "__main__":
    result = transcribe_and_translate(sys.argv[1])
    print(json.dumps(result))
