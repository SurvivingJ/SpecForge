import json
import os
import uuid
import zipfile
import io
import threading
import queue
from datetime import datetime

from flask import Flask, request, jsonify, Response, send_file, render_template
from langgraph.types import Command

from config import get_llm, HAIKU_MODEL, PROJECTS_DIR
from graph.graph import create_compiled_graph

app = Flask(__name__)

# Global graph and checkpointer (initialised once)
compiled_graph, checkpointer = create_compiled_graph()

# SSE event queues per project (thread-safe)
event_queues: dict[str, list[queue.Queue]] = {}
event_queues_lock = threading.Lock()

# Track graph execution threads
execution_threads: dict[str, threading.Thread] = {}


def emit_event(project_id: str, agent: str, message: str):
    """Push an SSE event to all listeners for a project."""
    event = {
        "agent": agent,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    with event_queues_lock:
        if project_id in event_queues:
            for q in event_queues[project_id]:
                q.put(event)


def run_graph(project_id: str, input_data: dict = None, resume_value=None):
    """Run or resume the graph in a background thread."""
    config = {"configurable": {"thread_id": project_id}}

    try:
        if input_data:
            emit_event(project_id, "System", "Starting project analysis...")
            for event in compiled_graph.stream(input_data, config, stream_mode="updates"):
                for node_name, update in event.items():
                    emit_event(project_id, node_name, f"Completed processing")
        elif resume_value is not None:
            emit_event(project_id, "System", "Processing your answers...")
            for event in compiled_graph.stream(
                Command(resume=resume_value), config, stream_mode="updates"
            ):
                for node_name, update in event.items():
                    emit_event(project_id, node_name, f"Completed processing")
    except Exception as e:
        emit_event(project_id, "System", f"Error: {str(e)}")

    emit_event(project_id, "System", "Ready")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json()
    idea = data.get("idea_description", "")
    depth = data.get("depth", "medium")

    if not idea.strip():
        return jsonify({"error": "idea_description is required"}), 400
    if depth not in ("shallow", "medium", "deep", "abyss"):
        return jsonify({"error": "depth must be shallow, medium, deep, or abyss"}), 400

    project_id = str(uuid.uuid4())

    # Create project directory
    project_dir = os.path.join(PROJECTS_DIR, project_id, "wiki")
    os.makedirs(project_dir, exist_ok=True)

    # Initialise SSE queue
    with event_queues_lock:
        event_queues[project_id] = []

    # Run graph in background thread
    input_data = {
        "idea_description": idea,
        "depth": depth,
        "shadow_wiki": {},
        "active_files": [],
        "current_questions": [],
        "pending_answers": [],
        "question_history": [],
        "round_number": 0,
        "depth_quota_remaining": 0,
        "is_complete": False,
        "active_agents": [],
        "lint_warnings": [],
    }

    thread = threading.Thread(target=run_graph, args=(project_id, input_data))
    thread.daemon = True
    thread.start()
    execution_threads[project_id] = thread

    return jsonify({"project_id": project_id, "thread_id": project_id}), 201


@app.route("/api/projects/<project_id>/questions", methods=["GET"])
def get_questions(project_id):
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
    except Exception:
        return jsonify({"status": "not_found"}), 404

    # Check if graph is at an interrupt
    if state.next:
        # Graph is paused — extract interrupt payload
        interrupt_data = None
        if hasattr(state, "tasks") and state.tasks:
            for task in state.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interrupt_data = task.interrupts[0].value
                    break

        if interrupt_data:
            return jsonify({
                "status": "questions_ready",
                "questions": interrupt_data.get("questions", []),
                "round": interrupt_data.get("round", 0),
                "wiki_status": interrupt_data.get("wiki_status", []),
            })

    # Check if graph is complete
    values = state.values
    if values.get("is_complete"):
        return jsonify({"status": "complete"})

    # Still processing
    return jsonify({"status": "processing"})


@app.route("/api/projects/<project_id>/answers", methods=["POST"])
def submit_answers(project_id):
    data = request.get_json()
    answers = data.get("answers", [])

    if not answers:
        return jsonify({"error": "answers are required"}), 400

    # Resume graph in background
    thread = threading.Thread(target=run_graph, args=(project_id, None, answers))
    thread.daemon = True
    thread.start()
    execution_threads[project_id] = thread

    return jsonify({"status": "processing"})


@app.route("/api/projects/<project_id>/status", methods=["GET"])
def project_status_sse(project_id):
    """SSE endpoint for real-time agent activity events."""
    q = queue.Queue()

    with event_queues_lock:
        if project_id not in event_queues:
            event_queues[project_id] = []
        event_queues[project_id].append(q)

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield f": keepalive\n\n"
        except GeneratorExit:
            with event_queues_lock:
                if project_id in event_queues and q in event_queues[project_id]:
                    event_queues[project_id].remove(q)

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/projects/<project_id>/wiki", methods=["GET"])
def get_wiki(project_id):
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
        wiki = state.values.get("shadow_wiki", {})
        return jsonify({"files": wiki})
    except Exception:
        return jsonify({"error": "Project not found"}), 404


@app.route("/api/projects/<project_id>/finalise", methods=["POST"])
def finalise_project(project_id):
    # Resume the graph with a signal to complete
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
        # Update state to mark as complete, then resume
        compiled_graph.update_state(config, {"is_complete": True})

        # Resume with empty answers to flow to finaliser
        thread = threading.Thread(target=run_graph, args=(project_id, None, []))
        thread.daemon = True
        thread.start()

        return jsonify({"status": "finalising"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/export", methods=["GET"])
def export_project(project_id):
    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
        wiki = state.values.get("shadow_wiki", {})

        # Write files to disk
        project_dir = os.path.join(PROJECTS_DIR, project_id, "wiki")
        os.makedirs(project_dir, exist_ok=True)
        for filename, content in wiki.items():
            filepath = os.path.join(project_dir, filename)
            with open(filepath, "w") as f:
                f.write(content)

        # Create zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in wiki.items():
                zf.writestr(filename, content)

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{project_id}_spec.zip",
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/respec", methods=["POST"])
def respec_section(project_id):
    data = request.get_json()
    file = data.get("file", "")
    selected_text = data.get("selected_text", "")
    instruction = data.get("instruction", "")

    if not all([file, selected_text, instruction]):
        return jsonify({"error": "file, selected_text, and instruction are required"}), 400

    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
        wiki = state.values.get("shadow_wiki", {})

        from graph.nodes.respec_agent import respec
        updated_content = respec(wiki, file, selected_text, instruction)

        # Update the wiki in the graph state
        new_wiki = dict(wiki)
        new_wiki[file] = updated_content
        compiled_graph.update_state(config, {"shadow_wiki": new_wiki})

        return jsonify({"updated_content": updated_content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/query_wiki", methods=["POST"])
def query_wiki(project_id):
    data = request.get_json()
    question = data.get("question", "")

    if not question.strip():
        return jsonify({"error": "question is required"}), 400

    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
        wiki = state.values.get("shadow_wiki", {})

        wiki_context = ""
        for fname, content in wiki.items():
            wiki_context += f"\n--- {fname} ---\n{content}\n"

        llm = get_llm(HAIKU_MODEL)
        response = llm.invoke([
            {"role": "system", "content": (
                "You are a helpful assistant. The user is building a project specification. "
                "Answer their question based on the following wiki content. "
                "If the information hasn't been documented yet, say so clearly."
            )},
            {"role": "user", "content": f"## Wiki Content\n{wiki_context}\n\n## Question\n{question}"},
        ])

        return jsonify({"answer": response.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/projects/<project_id>/break_down_question", methods=["POST"])
def break_down_question(project_id):
    data = request.get_json()
    question_id = data.get("question_id", "")

    if not question_id:
        return jsonify({"error": "question_id is required"}), 400

    config = {"configurable": {"thread_id": project_id}}

    try:
        state = compiled_graph.get_state(config)
        questions = state.values.get("current_questions", [])
        wiki = state.values.get("shadow_wiki", {})

        # Find the target question
        target_question = None
        for q in questions:
            if q.get("id") == question_id:
                target_question = q
                break

        if not target_question:
            return jsonify({"error": "Question not found"}), 404

        # Use LLM to decompose
        llm = get_llm(HAIKU_MODEL)
        response = llm.invoke([
            {"role": "system", "content": (
                "You are a question decomposition agent. Given a broad question about a project, "
                "break it into 2-3 more specific, focused sub-questions. "
                "Each sub-question should be answerable independently. "
                "Return valid JSON only.\n\n"
                '{"sub_questions": [{"id": "...", "text": "...", "type": "short_answer", '
                '"target_file": "...", "agent": "...", "options": null}]}'
            )},
            {"role": "user", "content": (
                f"Broad question: {target_question['text']}\n"
                f"Agent: {target_question.get('agent', 'unknown')}\n"
                f"Target file: {target_question.get('target_file', 'unknown')}"
            )},
        ])

        content = response.content
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result = json.loads(content)
        sub_questions = result.get("sub_questions", [])

        # Assign unique IDs
        for i, sq in enumerate(sub_questions):
            sq["id"] = f"{question_id}_sub{i+1}"

        # Update graph state: replace broad question with sub-questions
        new_questions = []
        for q in questions:
            if q.get("id") == question_id:
                new_questions.extend(sub_questions)
            else:
                new_questions.append(q)

        compiled_graph.update_state(config, {"current_questions": new_questions})

        return jsonify({"sub_questions": sub_questions})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    app.run(debug=True, port=5000, threaded=True)
