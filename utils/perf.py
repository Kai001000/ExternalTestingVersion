import json
import time
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

from .config import BASE_DIR


_TIMING_LOG_PATH = BASE_DIR / "logs" / "page_timings.jsonl"


class PagePerf:
    def __init__(self, page_name: str):
        self.page_name = page_name
        self.page_start = time.perf_counter()
        self.stage_timings: list[dict[str, float | str]] = []

    @contextmanager
    def track(self, stage: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.stage_timings.append(
                {
                    "stage": stage,
                    "seconds": round(time.perf_counter() - started, 6),
                }
            )

    def log(self, **extra) -> dict[str, object]:
        payload = {
            "page": self.page_name,
            "total_seconds": round(time.perf_counter() - self.page_start, 6),
            "stages": self.stage_timings,
        }
        if extra:
            payload.update(extra)

        _TIMING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TIMING_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")

        print(f"[page-timing] {json.dumps(payload, ensure_ascii=True)}")
        return payload


def render_internal_timing_summary(payload: dict[str, object], *, enabled: bool) -> None:
    if not enabled:
        return

    stage_rows = payload.get("stages", [])
    if not stage_rows:
        return

    stage_label = ", ".join(
        f"{row['stage']}: {float(row['seconds']):.2f}s"
        for row in stage_rows
    )
    st.caption(f"Timing: total {float(payload['total_seconds']):.2f}s | {stage_label}")
