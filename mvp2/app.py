"""
Rextag Lead Gen AI — MVP2 Backend
Flask server that:
  1. Serves the frontend dashboard
  2. Runs the 6-stage lead generation pipeline
  3. Provides SSE (Server-Sent Events) for real-time progress
  4. Returns results as JSON
"""

import json
import os
import sys
import threading
import time
from queue import Queue
from flask import Flask, Response, request, jsonify, send_from_directory
from flask_cors import CORS

# ── allow importing pipeline modules from this directory ─────
CURRENT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CURRENT)

# ── allow importing from parent directory (my_llm.py, crawler.py)
PARENT = os.path.abspath(os.path.join(CURRENT, ".."))
sys.path.insert(0, PARENT)

from pipeline import run_pipeline

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# ── Global state for pipeline progress/results ──────────────
pipeline_state = {
    "running": False,
    "progress_queue": Queue(),
    "results": None,
    "error": None,
}


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the frontend dashboard."""
    return send_from_directory(CURRENT, "index.html")


@app.route("/start", methods=["POST"])
def start_pipeline():
    """
    Start the lead generation pipeline in a background thread.
    Returns immediately with 202 Accepted.
    The frontend should connect to /progress SSE to follow along.
    """
    if pipeline_state["running"]:
        return jsonify({"error": "Pipeline already running"}), 409

    pipeline_state["running"] = True
    pipeline_state["results"] = None
    pipeline_state["error"] = None
    # Drain old progress messages
    while not pipeline_state["progress_queue"].empty():
        pipeline_state["progress_queue"].get_nowait()

    def _run():
        try:
            def on_progress(stage_id, pct, label, stats):
                pipeline_state["progress_queue"].put({
                    "type": "progress",
                    "stage": stage_id,
                    "pct": pct,
                    "label": label,
                    "stats": stats.copy(),
                })

            result = run_pipeline(on_progress=on_progress)
            pipeline_state["results"] = result
            pipeline_state["progress_queue"].put({
                "type": "complete",
                "leads_count": len(result["leads"]),
                "stats": result["stats"],
            })
        except Exception as exc:
            pipeline_state["error"] = str(exc)
            pipeline_state["progress_queue"].put({
                "type": "error",
                "message": str(exc),
            })
        finally:
            pipeline_state["running"] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"status": "started"}), 202


@app.route("/progress")
def progress_stream():
    """
    SSE endpoint for real-time pipeline progress.
    Frontend connects here after calling POST /start.
    """
    def generate():
        while True:
            try:
                msg = pipeline_state["progress_queue"].get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"

                if msg.get("type") in ("complete", "error"):
                    break
            except Exception:
                # Timeout — send heartbeat
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                # If pipeline stopped running, end the stream
                if not pipeline_state["running"]:
                    break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/results")
def get_results():
    """Return the latest pipeline results."""
    if pipeline_state["results"] is None:
        return jsonify({"error": "No results yet. Run the pipeline first."}), 404

    return jsonify(pipeline_state["results"])


@app.route("/status")
def get_status():
    """Return current pipeline status."""
    return jsonify({
        "running": pipeline_state["running"],
        "has_results": pipeline_state["results"] is not None,
        "error": pipeline_state["error"],
    })


# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  Rextag Lead Gen AI — MVP2")
    print("  http://localhost:5001")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5001, threaded=True)
