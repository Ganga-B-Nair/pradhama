"""Run once at H0 on the demo machine to pick the hardware profile
(docs/HACKATHON_PLAN.md §4). Confirmed CPU-only for this event, so this
mainly times the CPU-only row: faster-whisper `small` (int8) and
`qwen2.5:3b-instruct` via Ollama.

Usage: python scripts/bench.py path/to/demo_clip.wav
"""
import sys
import time

import requests


def bench_asr(audio_path: str) -> float:
    from faster_whisper import WhisperModel  # local import: only load when benchmarking

    start = time.time()
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, task="transcribe", language="ml")
    list(segments)  # force evaluation
    return time.time() - start


def bench_llm(prompts: list[str], model: str = "qwen2.5:3b-instruct", host: str = "http://localhost:11434") -> list[float]:
    times = []
    for prompt in prompts:
        start = time.time()
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        times.append(time.time() - start)
    return times


if __name__ == "__main__":
    clip = sys.argv[1] if len(sys.argv) > 1 else None
    if clip:
        print(f"ASR (small, cpu, int8): {bench_asr(clip):.1f}s")
    else:
        print("No audio clip given — skipping ASR benchmark")

    prompts = [
        "Extract the events from this text as JSON: 'I called the bank at 4pm and shared my OTP.'",
        "Summarize: a cyber-fraud complaint involving four UPI transactions totalling 1,60,000 rupees.",
        "List BNS sections that could apply to cheating by personation.",
    ]
    llm_times = bench_llm(prompts)
    print(f"LLM (qwen2.5:3b-instruct, cpu): {llm_times} -> avg {sum(llm_times)/len(llm_times):.1f}s")
