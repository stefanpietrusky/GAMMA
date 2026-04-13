"""
title: GAMMA V2 [GAME AUTOMATED MECHANICS MODIFICATION & ADAPTATION]
author: stefanpietrusky
author_url: https://downchurch.studio/
version: 2.0
"""

import os, re, json
import yaml
import requests
from datetime import datetime
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv

load_dotenv()

OLLAMA_CLOUD_MODEL = "gpt-oss:120b-cloud"
OLLAMA_CLOUD_API_KEY = os.getenv("OLLAMA_CLOUD_API_KEY", "").strip()
OLLAMA_CLOUD_BASE_URL = os.getenv("OLLAMA_CLOUD_BASE_URL", "https://api.ollama.com").rstrip("/")
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "180"))

if not OLLAMA_CLOUD_API_KEY:
    raise RuntimeError("OLLAMA_CLOUD_API_KEY was not found in the .env file.")

app = Flask(__name__)

@app.route('/list-objects', methods=['POST'])
def list_objects():
    data = request.json
    project_dir = data.get("project_dir", "").strip()
    if not project_dir:
        return jsonify({"error": "Please enter the project directory."}), 400

    objects_path = os.path.join(project_dir, "objects")
    if not os.path.isdir(objects_path):
        return jsonify({"error": f"Folder not found: {objects_path}"}), 404

    try:
        subdirs = [
            name for name in os.listdir(objects_path)
            if os.path.isdir(os.path.join(objects_path, name))
        ]
        return jsonify(subdirs)
    except Exception as e:
        return jsonify({"error": f"Error when reading out the object folders: {e}"}), 500

EVENT_ORDER = {
    "PreCreate": 0,
    "Create": 1,
    "Destroy": 2,
    "CleanUp": 3,

    "Alarm": 10,

    "BeginStep": 20,
    "Step": 21,
    "EndStep": 22,

    "Collision": 30,
    "Keyboard": 40,
    "KeyPress": 41,
    "KeyRelease": 42,
    "Mouse": 50,

    "Other": 60,

    "PreDraw": 70,
    "DrawBegin": 71,
    "Draw": 72,
    "DrawEnd": 73,
    "PostDraw": 74,
    "DrawGUIBegin": 75,
    "DrawGUI": 76,
    "DrawGUIEnd": 77,

    "Trigger": 80,
    "Gesture": 90
}

def parse_event_filename(filename):
    match = re.match(r'^([A-Za-z]+)_(\d+)\.gml$', filename)
    if match:
        event_name = match.group(1).strip()
        event_index = int(match.group(2))
        return event_name, event_index

    return filename.replace(".gml", "").strip(), None

APP_DIR = os.path.dirname(os.path.abspath(__file__))
COMBINED_CODE_FILENAME = "all_objects_combined.gml"


def build_all_objects_summary(project_dir: str) -> str:
    objects_dir = os.path.join(project_dir, "objects")
    if not os.path.isdir(objects_dir):
        raise FileNotFoundError(f"Folder not found: {objects_dir}")

    output_file = os.path.join(APP_DIR, COMBINED_CODE_FILENAME)
    obj_events = {}

    for root, _, files in os.walk(objects_dir):
        rel = os.path.relpath(root, objects_dir).split(os.sep)
        if not rel or rel[0] in (".", ""):
            continue

        obj = rel[0]

        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in (".gml", ".yml", ".yaml"):
                continue

            full = os.path.join(root, fname)
            base = os.path.splitext(fname)[0]
            event = base.split("_", 1)[0]

            obj_events.setdefault(obj, {}) \
                      .setdefault(event, []) \
                      .append((full, ext))

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("// ======================================================\n")
        out.write("// Combined GML code of all objects\n")
        out.write(f"// Generated on: {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        out.write(f"// Project: {project_dir}\n")
        out.write("// ======================================================\n\n")

        for obj in sorted(obj_events):
            out.write(f"// === Object: {obj} ===\n\n")
            for event in sorted(obj_events[obj]):
                out.write(f"// --- Event: {event} ---\n")
                for path, ext in sorted(obj_events[obj][event], key=lambda x: x[0]):
                    out.write(f"// File: {os.path.basename(path)}\n")
                    if ext == ".gml":
                        with open(path, "r", encoding="utf-8") as f:
                            out.write(f.read().rstrip() + "\n\n")
                    else:
                        with open(path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}
                        code = data.get("gml", "")
                        out.write(code.rstrip() + "\n\n")

            out.write("\n")

        out.write("// === End of all objects ===\n")

    return output_file


def read_combined_summary() -> str:
    summary_path = os.path.join(APP_DIR, COMBINED_CODE_FILENAME)
    if not os.path.isfile(summary_path):
        return ""

    with open(summary_path, "r", encoding="utf-8") as f:
        text = f.read()

    text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    return text

@app.route('/object-events', methods=['POST'])
def object_events():
    data = request.json
    project_dir = data.get("project_dir", "").strip()
    object_name = data.get("object_name", "").strip()

    if not project_dir or not object_name:
        return jsonify({"error": "Project directory and object name are required."}), 400

    object_path = os.path.join(project_dir, "objects", object_name)
    if not os.path.isdir(object_path):
        return jsonify({"error": f"Object folder not found: {object_path}"}), 404

    try:
        gml_files = [
            name for name in os.listdir(object_path)
            if name.lower().endswith(".gml")
        ]

        sorted_files = sorted(
            gml_files,
            key=lambda fn: (
                EVENT_ORDER.get(parse_event_filename(fn)[0], 999),
                parse_event_filename(fn)[1] if parse_event_filename(fn)[1] is not None else 9999,
                fn.lower()
            )
        )

        events = []
        for filename in sorted_files:
            event_name, event_index = parse_event_filename(filename)
            events.append({
                "filename": filename,
                "label": filename.replace(".gml", ""),
                "event_name": event_name,
                "event_index": event_index
            })

        return jsonify({
            "object_name": object_name,
            "events": events
        })

    except Exception as e:
        return jsonify({"error": f"Error while reading the event files: {e}"}), 500

@app.route('/build-project-summary', methods=['POST'])
def build_project_summary():
    data = request.json
    project_dir = data.get("project_dir", "").strip()

    if not project_dir:
        return jsonify({"error": "Please enter the project directory."}), 400

    try:
        output_file = build_all_objects_summary(project_dir)
        return jsonify({
            "status": "Project summary successfully created.",
            "output_file": output_file,
            "filename": os.path.basename(output_file)
        })
    except Exception as e:
        return jsonify({"error": f"Error while creating the project summary: {e}"}), 500

@app.route('/project-chat', methods=['POST'])
def project_chat():
    data = request.json
    user_message = data.get("message", "").strip()
    project_dir = data.get("project_dir", "").strip()
    object_name = data.get("object_name", "").strip()

    if not user_message:
        return jsonify({"error": "Please enter a message."}), 400

    summary_text = read_combined_summary()
    if not summary_text:
        return jsonify({
            "error": "No code summary found yet. Please enter a valid project path first."
        }), 400

    prompt = f"""
    You are an assistant for adapting and improving a GameMaker project.

    Project directory:
    {project_dir}

    Currently selected object:
    {object_name}

    Below is a combined code summary of all object code in the project:

    {summary_text}

    User question:
    {user_message}

    Please follow these rules:
    1. Answer in German.
    2. Be practical and concise.
    3. Use clean Markdown formatting.
    3a. Do not use Markdown tables.
    3b. Use bullet lists instead of tables.
    4. Do not use XML-style tags such as <think>.
    5. Do not use decorative symbols or unnecessary special characters.
    6. When suggesting code changes, use this structure:
    - Vorher
    - Nachher
    - Warum die Änderung sinnvoll ist
    7. Mention the object/event that should be changed whenever possible.
    8. Use code fences only for actual GML or code snippets.

    Task:
    - Analyze the existing object/event structure.
    - Suggest concrete improvements.
    - Provide nachvollziehbare vorher/nachher changes where useful.
    """

    try:
        answer = call_ollama_cloud(prompt)
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": f"Ollama-Cloud-Error: {e}"}), 500

@app.route('/event-content', methods=['POST'])
def event_content():
    data = request.json
    project_dir = data.get("project_dir", "").strip()
    object_name = data.get("object_name", "").strip()
    filename = data.get("filename", "").strip()

    if not project_dir or not object_name or not filename:
        return jsonify({"error": "Project directory, object name and filename are required."}), 400

    file_path = os.path.join(project_dir, "objects", object_name, filename)

    if not os.path.isfile(file_path):
        return jsonify({"error": f"Event file not found: {file_path}"}), 404

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return jsonify({
            "filename": filename,
            "content": content
        })
    except Exception as e:
        return jsonify({"error": f"Error while reading the event file: {e}"}), 500

@app.route('/save-event', methods=['POST'])
def save_event():
    data = request.json
    project_dir = data.get("project_dir", "").strip()
    object_name = data.get("object_name", "").strip()
    filename = data.get("filename", "").strip()
    content = data.get("content", "")

    if not project_dir or not object_name or not filename:
        return jsonify({"error": "Project directory, object name and filename are required."}), 400

    file_path = os.path.join(project_dir, "objects", object_name, filename)

    if not os.path.isfile(file_path):
        return jsonify({"error": f"Event file not found: {file_path}"}), 404

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        summary_file = build_all_objects_summary(project_dir)

        return jsonify({
            "status": "Event file successfully saved",
            "path": file_path,
            "summary_file": summary_file
        })
    except Exception as e:
        return jsonify({"error": f"Error while saving the event file: {e}"}), 500

def clean_model_response(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.strip()
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text

def call_ollama_cloud(prompt: str) -> str:
    if not OLLAMA_CLOUD_API_KEY:
        raise RuntimeError("OLLAMA_CLOUD_API_KEY was not found in the .env file.")

    headers = {
        "Authorization": f"Bearer {OLLAMA_CLOUD_API_KEY}"
    }

    url = f"{OLLAMA_CLOUD_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_CLOUD_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.5,
            "num_ctx": 8192
        }
    }

    resp = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=(10, OLLAMA_TIMEOUT_SEC)
    )
    resp.raise_for_status()

    data = resp.json()
    raw_text = (data.get("response") or "").strip()
    return clean_model_response(raw_text)

def extract_outer_json(text: str) -> str:
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

def extract_event_reference_map(summary_text: str) -> dict:
    object_names = re.findall(r"// === Object: ([^=\n]+) ===", summary_text or "")
    known = {name.strip() for name in object_names if name.strip()}
    event_map = {}

    section_pattern = re.compile(
        r"// === Object: ([^=\n]+) ===\n\n(.*?)(?=\n// === Object: |\n// === End of all objects ===)",
        re.DOTALL
    )
    event_pattern = re.compile(
        r"// --- Event: ([^\n]+) ---\n(.*?)(?=\n// --- Event: |\Z)",
        re.DOTALL
    )

    for match in section_pattern.finditer(summary_text or ""):
        source_obj = match.group(1).strip()
        block = match.group(2)

        for event_match in event_pattern.finditer(block):
            event_name = event_match.group(1).strip()
            event_block = event_match.group(2)

            refs = sorted(set(re.findall(r"\b(obj_[A-Za-z0-9_]+|o_[A-Za-z0-9_]+)\b", event_block)))
            for target_obj in refs:
                if target_obj in known and target_obj != source_obj:
                    event_map.setdefault((source_obj, target_obj), set()).add(event_name)

    return {key: sorted(values) for key, values in event_map.items()}


def enrich_graph_with_event_data(graph: dict, summary_text: str) -> dict:
    if not isinstance(graph, dict):
        return {"nodes": [], "edges": []}

    event_map = extract_event_reference_map(summary_text)
    edges_out = []

    for edge in graph.get("edges", []) or []:
        if not isinstance(edge, dict):
            continue

        src = (edge.get("from") or "").strip()
        tgt = (edge.get("to") or "").strip()
        label = (edge.get("label") or "related_to").strip()
        title = (edge.get("title") or label).strip()

        event_names = edge.get("event_names") or event_map.get((src, tgt), [])

        if event_names:
            events_text = ", ".join(event_names)
            if "Events:" not in title and "Referenz in Events:" not in title:
                title = f"{title}\nEvents: {events_text}" if title else f"Events: {events_text}"

        edges_out.append({
            "from": src,
            "to": tgt,
            "label": label,
            "title": title,
            "event_names": event_names
        })

    return {
        "nodes": graph.get("nodes", []) or [],
        "edges": edges_out
    }


def filter_connected_nodes(graph: dict, selected_object: str = "", keep_selected: bool = True) -> dict:
    if not isinstance(graph, dict):
        return {"nodes": [], "edges": []}

    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []

    connected_ids = set()
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src = (edge.get("from") or "").strip()
        tgt = (edge.get("to") or "").strip()
        if src:
            connected_ids.add(src)
        if tgt:
            connected_ids.add(tgt)

    if keep_selected and selected_object:
        connected_ids.add(selected_object)

    filtered_nodes = []
    valid_ids = set()

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = (node.get("id") or "").strip()
        if node_id and node_id in connected_ids:
            filtered_nodes.append(node)
            valid_ids.add(node_id)

    filtered_edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src = (edge.get("from") or "").strip()
        tgt = (edge.get("to") or "").strip()
        if src in valid_ids and tgt in valid_ids:
            filtered_edges.append(edge)

    return {
        "nodes": filtered_nodes,
        "edges": filtered_edges
    }

def normalize_project_graph(graph: dict, selected_object: str = "") -> dict:
    if not isinstance(graph, dict):
        return {"nodes": [], "edges": []}

    nodes_in = graph.get("nodes", []) or []
    edges_in = graph.get("edges", []) or []

    nodes = []
    node_ids = set()

    for node in nodes_in:
        if not isinstance(node, dict):
            continue

        node_id = (node.get("id") or node.get("label") or "").strip()
        label = (node.get("label") or node_id).strip()
        title = (node.get("title") or label).strip()

        if not node_id or node_id in node_ids:
            continue

        item = {
            "id": node_id,
            "label": label,
            "title": title
        }

        if selected_object and node_id == selected_object:
            item["is_selected"] = True

        nodes.append(item)
        node_ids.add(node_id)

    edge_map = {}

    for edge in edges_in:
        if not isinstance(edge, dict):
            continue

        src = (edge.get("from") or "").strip()
        tgt = (edge.get("to") or "").strip()
        label = (edge.get("label") or "related_to").strip()
        title = (edge.get("title") or label).strip()
        event_names = sorted({
            str(name).strip()
            for name in (edge.get("event_names") or [])
            if str(name).strip()
        })

        if not src or not tgt or src not in node_ids or tgt not in node_ids or src == tgt:
            continue

        key = (src, tgt, label)

        if key not in edge_map:
            edge_map[key] = {
                "from": src,
                "to": tgt,
                "label": label,
                "title": title,
                "event_names": event_names
            }
        else:
            existing = edge_map[key]
            existing["event_names"] = sorted(set(existing.get("event_names", [])) | set(event_names))
            if not existing.get("title") and title:
                existing["title"] = title

    edges = list(edge_map.values())

    return filter_connected_nodes(
        {"nodes": nodes, "edges": edges},
        selected_object=selected_object,
        keep_selected=True
    )

def build_project_graph_fallback(summary_text: str, selected_object: str = "") -> dict:
    object_names = re.findall(r"// === Object: ([^=\n]+) ===", summary_text or "")
    object_names = [name.strip() for name in object_names if name.strip()]

    nodes = []
    for obj in object_names:
        node = {
            "id": obj,
            "label": obj,
            "title": obj
        }
        if selected_object and obj == selected_object:
            node["is_selected"] = True
        nodes.append(node)

    event_map = extract_event_reference_map(summary_text)
    edges = []

    for (source_obj, target_obj), event_names in sorted(event_map.items()):
        edges.append({
            "from": source_obj,
            "to": target_obj,
            "label": "references",
            "title": f"Referenz in Events: {', '.join(event_names)}",
            "event_names": event_names
        })

    return filter_connected_nodes(
        {"nodes": nodes, "edges": edges},
        selected_object=selected_object,
        keep_selected=True
    )

def build_project_knowledge_graph(project_dir: str, selected_object: str = "") -> dict:
    summary_text = read_combined_summary()

    if not summary_text.strip():
        build_all_objects_summary(project_dir)
        summary_text = read_combined_summary()

    if not summary_text.strip():
        return {"nodes": [], "edges": []}

    prompt = f"""
    You analyze a GameMaker project summary and return ONLY valid JSON.

    Task:
    Create a knowledge graph of the project structure based on the combined object code.

    Important rules:
    - Return JSON only.
    - No markdown.
    - No explanations.
    - Focus mainly on GameMaker objects as nodes.
    - Create edges only where an interaction or dependency is plausible from the code.
    - Good edge labels are for example:
    creates, destroys, collides_with, references, controls, depends_on, calls, changes_room_to, inherits_from
    - Keep labels short.
    - Maximum 80 nodes.
    - Maximum 140 edges.

    Selected object:
    {selected_object or "none"}

    Required JSON schema:
    {{
    "nodes": [
        {{
        "id": "obj_player",
        "label": "obj_player",
        "title": "short description"
        }}
    ],
    "edges": [
        {{
        "from": "obj_player",
        "to": "obj_enemy",
        "label": "collides_with",
        "title": "evidence or context"
        }}
    ]
    }}

    Project summary:
    {summary_text}
    """.strip()

    try:
        raw = call_ollama_cloud(prompt)
        parsed = json.loads(extract_outer_json(raw))
        normalized = normalize_project_graph(parsed, selected_object)
        enriched = enrich_graph_with_event_data(normalized, summary_text)

        if enriched.get("nodes"):
            return enriched
    except Exception:
        pass

    fallback = build_project_graph_fallback(summary_text, selected_object)
    return enrich_graph_with_event_data(fallback, summary_text)

@app.route('/project-knowledge-graph', methods=['POST'])
def project_knowledge_graph():
    data = request.json or {}
    project_dir = data.get("project_dir", "").strip()
    object_name = data.get("object_name", "").strip()

    if not project_dir:
        return jsonify({"error": "Project directory is required."}), 400

    try:
        graph = build_project_knowledge_graph(project_dir, object_name)
        return jsonify(graph)
    except Exception as e:
        return jsonify({"error": f"Error while creating the project knowledge graph: {e}"}), 500

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GAMMA</title>
    <link rel="stylesheet" href="/styles.css">
    <script defer src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head>
<body>
    <div class="container">
        <div class="logo-wrapper">
            <img src="/static/GAMMA_LOGO.png" alt="GAMMA Logo" class="app-logo">
        </div>
        <h1>GAMMA</h1>
            
        <div class="form-section">
        <label for="project-dir-input">Project folder (path):</label>
        <input type="text" id="project-dir-input" placeholder="z. B. C:\GameMaker\MyProject" />
        </div>

        <div class="form-section">
        <label for="object-select">Object folder:</label>
        <select id="object-select">
            <option value="" disabled selected>Select a folder...</option>
        </select>
        </div>

        <h2 id="project-graph-title" style="display:none;">PROJECT KNOWLEDGE GRAPH</h2>
        <div id="project-knowledge-graph" style="display:none;"></div>
        <div id="graph-connection-info" class="graph-connection-info" style="display:none;"></div>

        <div id="object-events-container" class="result-container" style="display:none;">
            <h2>OBJECT EVENTS</h2>

            <div id="event-buttons" class="event-buttons"></div>

            <div id="event-editor-container" style="display:none; margin-top:15px;">
                <label for="event-editor"><strong>Selected event:</strong> <span id="selected-event-name"></span></label>
                <textarea id="event-editor" rows="18" spellcheck="false"></textarea>
                <button id="save-event-btn" type="button">Save event</button>
            </div>

            <div id="project-chat-container" style="display:block; margin-top:25px;">
                <h2>PROJECT ADAPTATION CHAT</h2>
                <div id="chat-output" class="chat-output"></div>

                <div class="chat-input-row">
                    <textarea
                        id="chat-input"
                        rows="4"
                        placeholder="Ask how the project could be adapted, expanded or improved..."
                    ></textarea>
                    <button id="send-chat-btn" type="button">Send</button>
                </div>
            </div>
        </div>
        
        <div id="message-container" aria-live="polite"></div>
    </div>
    <script src="/script.js"></script>
</body>
</html>
"""

CSS_CONTENT = """
body {
    font-family: Arial, sans-serif;
    background-color: #f4f4f4;
    margin: 0;
    padding: 20px;
}

.container {
    width: 90%;
    max-width: 1200px;
    margin: auto;
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow:0 4px 12px rgba(0,0,0,0.3);
    border: 3px solid #262626;
}

h1, h2 {
    text-align: center;
    color: #333;
}

input[type="text"] {
    width: 100%;
    padding: 10px;
    border: 3px solid #262626;
    border-radius: 5px;
    box-sizing: border-box;
}

.result-container {
    background-color: #ffffff;
    border: 3px solid #262626;
    padding: 15px;
    border-radius: 8px;
    margin-top: 10px;
}

pre {
    background: #ffffff;
    padding: 10px;
    overflow-x: auto;
}

.form-section {
    margin-bottom: 20px;   
}

.form-section label {
    display: block;
    font-weight: 500;
    color: #262626;
    margin-bottom: 8px
}

.form-section input {
    width: 100%;
}

.difficulty-buttons {
    text-align: left;
}

input[type="text"],
select {
    width: 100%;
    padding: 10px;
    margin: 0;
    border: 3px solid #262626;
    border-radius: 5px;
    background-color: #f0f0f0;
    color: #262626;
    font-size: 1em;
    box-sizing: border-box;
}

input[type="text"],
select,
input[type="color"] {
    transition: border-color .2s ease, box-shadow .2s ease;
}

input[type="text"]:focus,
select:focus,
input[type="color"]:focus {
    outline: none; 
    border: 3px solid #00FFCC !important;  
    box-shadow: 0 0 0 3px rgba(0, 255, 204, 0.25);
}

#result-container pre,
#gml-output {
    font-family: Arial, sans-serif;
    color: #262626;
}

#message-container {
    min-height: 3em;  
    margin-top: 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.error {
    background-color: #ffffff;
    border: 3px solid #f44336;
    color: #f44336;
    padding: 10px 15px;
    border-radius: 4px;
    opacity: 1; 
    text-align: center;
}

.success {
    background-color: #00FFCC;
    border: 3px solid #262626;
    color: #262626;
    padding: 10px 15px;
    border-radius: 4px;
    opacity: 1;
    text-align: center;
}

.fade-out {
  animation: fadeOut 0.5s ease-out forwards;
}

@keyframes fadeOut {
  to {
    opacity: 0;
  }
}

.event-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 15px;
}

.event-button {
    padding: 8px 14px;
    border: 3px solid #262626;
    background-color: #ffffff;
    color: #262626;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.95rem;
}

.event-button:hover,
.event-button.active {
    background-color: #262626;
    color: #ffffff;
}

#event-editor {
    width: 100%;
    min-height: 350px;
    padding: 12px;
    border: 3px solid #262626;
    border-radius: 5px;
    box-sizing: border-box;
    font-family: Consolas, Monaco, monospace;
    font-size: 0.95rem;
    white-space: pre;
    overflow: auto;
    resize: vertical;
    background-color: #ffffff;
    color: #262626;
    margin-top: 8px;
    margin-bottom: 12px;
}

#event-editor:focus {
    outline: none;
    border: 3px solid #00FFCC !important;
    box-shadow: 0 0 0 3px rgba(0, 255, 204, 0.25);
}

#save-event-btn {
    padding: 10px 16px;
    border: 3px solid #262626;
    background-color: #ffffff;
    color: #262626;
    border-radius: 5px;
    cursor: pointer;
    font-size: 1em;
}

#save-event-btn:hover {
    background-color: #262626;
    color: #ffffff;
}

#project-knowledge-graph {
    display: none;
    width: 100%;
    height: 460px;
    margin-top: 10px;
    border: 3px solid #262626;
    border-radius: 12px;
    background: #ffffff;
    box-sizing: border-box;
}

.graph-connection-info {
    display: none;
    margin-top: 10px;
    padding: 14px;
    border: 3px solid #262626;
    border-radius: 8px;
    background: #ffffff;
    color: #262626;
}

.graph-connection-info h3 {
    margin: 0 0 10px 0;
}

.graph-connection-group {
    padding: 10px 0;
    border-top: 2px solid #e6e6e6;
}

.graph-connection-group:first-of-type {
    border-top: none;
    padding-top: 0;
}

#project-chat-container {
    border-top: 3px solid #262626;
    padding-top: 20px;
}

.chat-output {
    min-height: 180px;
    max-height: 420px;
    overflow-y: auto;
    border: 3px solid #262626;
    border-radius: 5px;
    background: #ffffff;
    padding: 12px;
    margin-bottom: 12px;
    white-space: pre-wrap;
}

.chat-message {
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 10px;
    line-height: 1.5;
}

.chat-message.user {
    background: #f0f0f0;
    border: 2px solid #262626;
}

.chat-message.assistant {
    background: #ffffff;
    border: 2px solid #00FFCC;
}

#chat-input {
    width: 100%;
    min-height: 100px;
    padding: 12px;
    border: 3px solid #262626;
    border-radius: 5px;
    box-sizing: border-box;
    font-family: Arial, sans-serif;
    font-size: 0.95rem;
    resize: vertical;
    margin-bottom: 12px;
}

#chat-input:focus {
    outline: none;
    border: 3px solid #00FFCC !important;
    box-shadow: 0 0 0 3px rgba(0, 255, 204, 0.25);
}

.chat-typing-plain {
    white-space: pre-wrap;
    word-break: break-word;
}

#send-chat-btn {
    padding: 10px 16px;
    border: 3px solid #262626;
    background-color: #ffffff;
    color: #262626;
    border-radius: 5px;
    cursor: pointer;
    font-size: 1em;
}

#send-chat-btn:hover {
    background-color: #262626;
    color: #ffffff;
}

.chat-message {
    padding: 12px 14px;
    border-radius: 8px;
    margin-bottom: 12px;
    line-height: 1.6;
}

.chat-label {
    font-weight: 700;
    margin-bottom: 6px;
    display: block;
    letter-spacing: 0.3px;
}

.chat-message.user .chat-label {
    color: #262626;
}

.chat-message.assistant .chat-label {
    color: #00FFCC;
}

.chat-body {
    white-space: normal;
    word-break: break-word;
}

.chat-body p {
    margin: 0 0 10px 0;
}

.chat-body p:last-child {
    margin-bottom: 0;
}

.chat-body h3,
.chat-body h4,
.chat-body h5 {
    margin: 14px 0 8px 0;
    color: #262626;
}

.chat-body ul {
    margin: 8px 0 10px 22px;
    padding: 0;
}

.chat-body li {
    margin-bottom: 6px;
}

.chat-body hr {
    border: none;
    border-top: 2px solid #262626;
    margin: 12px 0;
}

.chat-body code {
    background: #00FFCC;
    border: 2px solid #262626;
    border-radius: 2px;
    padding: 1px 5px;
    font-family: Consolas, Monaco, monospace;
    font-size: 0.92em;
}

.chat-body pre {
    background: #f7f7f7;
    border: 2px solid #262626;
    border-radius: 6px;
    padding: 12px;
    overflow-x: auto;
    margin: 10px 0;
}

.chat-body pre code {
    background: transparent;
    border: none;
    padding: 0;
}

.typing-cursor {
    display: inline-block;
    margin-left: 2px;
    animation: blinkCursor 0.8s steps(1) infinite;
    font-weight: bold;
}

@keyframes blinkCursor {
    50% {
        opacity: 0;
    }
}

.chat-loading {
    display: flex;
    align-items: center;
    gap: 10px;
}

.spinner {
    width: 18px;
    height: 18px;
    border: 3px solid #262626;
    border-top: 3px solid #00FFCC;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
}

@keyframes spin {
    to {
        transform: rotate(360deg);
    }
}

.send-disabled {
    opacity: 0.6;
    pointer-events: none;
}

.codeblock-wrapper {
    position: relative;
    margin: 10px 0;
}

.codeblock-toolbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    background: #f0f0f0;
    border: 2px solid #262626;
    border-bottom: none;
    border-radius: 6px 6px 0 0;
    padding: 6px 10px;
}

.codeblock-language {
    font-size: 0.85rem;
    color: #555;
    font-family: Consolas, Monaco, monospace;
    min-height: 1em;
}

.chat-body .codeblock-wrapper pre {
    margin: 0;
    border-top: none;
    border-radius: 0 0 6px 6px;
    padding-top: 12px;
}

.copy-code-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 34px;
    height: 34px;
    border: 2px solid #262626;
    background: #ffffff;
    border-radius: 5px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    z-index: 2;
}

.copy-code-btn:hover {
    background: #00FFCC;
}

.copy-code-btn img {
    width: 18px;
    height: 18px;
    pointer-events: none;
}

.copy-code-btn.copied {
    border-color: #00FFCC;
    box-shadow: 0 0 0 3px rgba(0, 255, 204, 0.25);
}

.chat-body pre {
    padding-top: 46px;
}

.event-ref-link {
    border: none;
    background: transparent;
    padding: 0;
    cursor: pointer;
}

.event-ref-link code {
    border: 1px solid #00FFCC;
    background: #eef9ff;
}

.event-ref-link:hover code {
    background: #dff4ff;
}

.chat-table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 14px 0;
    font-size: 0.95rem;
}

.chat-table th,
.chat-table td {
    border: 2px solid #262626;
    padding: 8px 10px;
    text-align: left;
    vertical-align: top;
}

.chat-table th {
    background: #f0f0f0;
    font-weight: 700;
}

.chat-table td {
    background: #ffffff;
}

.logo-wrapper {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-bottom: 12px;
}

.app-logo {
    display: block;
    max-width: 180px;
    width: 100%;
    height: auto;
}

"""

JS_CONTENT = """
document.addEventListener('DOMContentLoaded', function() {
    const projectDirInput = document.getElementById('project-dir-input');
    const objectSelect = document.getElementById('object-select');
    const objectEventsContainer = document.getElementById('object-events-container');
    const eventButtonsContainer = document.getElementById('event-buttons');
    const eventEditorContainer = document.getElementById('event-editor-container');
    const eventEditor = document.getElementById('event-editor');
    const selectedEventName = document.getElementById('selected-event-name');
    const saveEventBtn = document.getElementById('save-event-btn');

    const projectGraphContainer = document.getElementById('project-graph-container');
    const projectGraphTitle = document.getElementById('project-graph-title');
    const projectKnowledgeGraph = document.getElementById('project-knowledge-graph');
    const graphConnectionInfo = document.getElementById('graph-connection-info');

    const chatOutput = document.getElementById('chat-output');
    const chatInput = document.getElementById('chat-input');
    const sendChatBtn = document.getElementById('send-chat-btn');

    let currentEventFilename = "";
    let projectGraphNetwork = null;
    let projectGraphDataCache = null;
    let projectGraphNodes = null;
    let projectGraphEdges = null;

    projectDirInput.addEventListener('blur', async () => {
        const projectDir = projectDirInput.value.trim();
        if (!projectDir) return;

        try {
            projectGraphDataCache = null;
            destroyProjectKnowledgeGraph();
            clearGraphConnectionInfo();

            const [objectsRes, summaryRes] = await Promise.all([
                fetch('/list-objects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_dir: projectDir })
                }),
                fetch('/build-project-summary', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_dir: projectDir })
                })
            ]);

            const objectsData = await objectsRes.json();
            const summaryData = await summaryRes.json();

            if (objectsData.error) {
                showMessage("Fehler: " + objectsData.error, 'error');
                return;
            }

            if (summaryData.error) {
                showError("Fehler bei Code-Zusammenfassung: " + summaryData.error);
                return;
            }

            objectSelect.innerHTML = '<option value="" disabled selected>Wähle einen Ordner…</option>';
            objectsData.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                objectSelect.appendChild(opt);
            });

            showMessage("Code-Zusammenfassung erstellt: " + summaryData.filename, 'success', 2500);
            await refreshProjectKnowledgeGraph('', true);
        } catch (err) {
            console.error(err);
            showMessage("An error occurred while loading the project data.", 'error');
        }
    });

    objectSelect.addEventListener('change', function() {
        const projectDir = projectDirInput.value.trim();
        const objectName = objectSelect.value;

        eventButtonsContainer.innerHTML = '';
        eventEditor.value = '';
        selectedEventName.textContent = '';
        currentEventFilename = '';
        eventEditorContainer.style.display = 'none';
        clearGraphConnectionInfo();

        if (!projectDir || !objectName) {
            objectEventsContainer.style.display = 'none';
            updateProjectKnowledgeGraphSelection('');
            return;
        }

        fetch('/object-events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_dir: projectDir,
                object_name: objectName
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage("Fehler: " + data.error, 'error');
                objectEventsContainer.style.display = 'none';
                return;
            }

            const events = data.events || [];
            if (events.length === 0) {
                showError("No event files found for this object.");
                objectEventsContainer.style.display = 'none';
                updateProjectKnowledgeGraphSelection(objectName);
                return;
            }

            events.forEach(evt => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'event-button';
                btn.textContent = evt.label;
                btn.dataset.filename = evt.filename;

                btn.addEventListener('click', function() {
                    loadEventContent(evt.filename, btn);
                });

                eventButtonsContainer.appendChild(btn);
            });

            objectEventsContainer.style.display = 'block';
            updateProjectKnowledgeGraphSelection(objectName);
        })
        .catch(error => {
            console.error("Error while loading object events:", error);
            showError("An error occurred while loading the object events.");
            objectEventsContainer.style.display = 'none';
        });
    });

    function showMessage(msg, type = 'error', timeout_ms = 5000) {
        const container = document.getElementById('message-container');
        if (!container) return;

        container.innerHTML = '';

        const alertDiv = document.createElement('div');
        alertDiv.classList.add(type);
        alertDiv.textContent = msg;
        container.appendChild(alertDiv);

        setTimeout(() => {
            alertDiv.classList.add('fade-out');
            alertDiv.addEventListener('animationend', () => {
                if (container.contains(alertDiv)) container.removeChild(alertDiv);
            }, { once: true });
        }, timeout_ms);
    }

    function showError(msg, timeout_ms = 5000) {
        showMessage(msg, 'error', timeout_ms);
    }

    function clearGraphConnectionInfo() {
        if (!graphConnectionInfo) return;
        graphConnectionInfo.innerHTML = '';
        graphConnectionInfo.style.display = 'none';
    }

    function extractEventNamesFromEdge(edge) {
        if (!edge) return [];

        if (Array.isArray(edge.event_names) && edge.event_names.length) {
            return edge.event_names.filter(Boolean);
        }

        const title = String(edge.title || '');
        const match = title.match(/(?:Referenz in Events|Events):\s*(.+)$/i);
        if (!match) return [];

        return match[1]
            .split(',')
            .map(value => value.trim())
            .filter(Boolean);
    }

    function showGraphConnectionInfoForNode(nodeId) {
        if (!graphConnectionInfo || !projectGraphDataCache || !nodeId) return;

        const relatedEdges = (projectGraphDataCache.edges || []).filter(edge =>
            edge.from === nodeId || edge.to === nodeId
        );

        if (relatedEdges.length === 0) {
            graphConnectionInfo.innerHTML = `
                <h3>${escapeHtml(nodeId)}</h3>
                <p>Für dieses Objekt wurden keine Verbindungen gefunden.</p>
            `;
            graphConnectionInfo.style.display = 'block';
            return;
        }

        const items = relatedEdges.map(edge => {
            const otherNode = edge.from === nodeId ? edge.to : edge.from;
            const relation = escapeHtml(edge.label || 'related_to');
            const eventNames = extractEventNamesFromEdge(edge);

            return `
                <div class="graph-connection-group">
                    <div><strong>${escapeHtml(nodeId)}</strong> → <strong>${escapeHtml(otherNode)}</strong></div>
                    <div>Beziehung: ${relation}</div>
                    <div>Events: ${eventNames.length ? escapeHtml(eventNames.join(', ')) : 'Keine Event-Infos verfügbar'}</div>
                </div>
            `;
        }).join('');

        graphConnectionInfo.innerHTML = `
            <h3>Verbindungen für ${escapeHtml(nodeId)}</h3>
            ${items}
        `;
        graphConnectionInfo.style.display = 'block';
    }

    function updateProjectKnowledgeGraphSelection(selectedObject = '') {
        if (!projectGraphNodes) return;

        const updates = [];
        projectGraphNodes.forEach(node => {
            const isSelected = Boolean(selectedObject) && node.id === selectedObject;

            updates.push({
                id: node.id,
                size: isSelected ? 24 : 18,
                borderWidth: isSelected ? 4 : 2,
                color: {
                    background: '#ffffff',
                    border: isSelected ? '#00FFCC' : '#262626',
                    highlight: {
                        background: '#ffffff',
                        border: isSelected ? '#00FFCC' : '#262626'
                    },
                    hover: {
                        background: '#ffffff',
                        border: isSelected ? '#00FFCC' : '#262626'
                    }
                }
            });
        });

        projectGraphNodes.update(updates);

        if (projectGraphNetwork) {
            if (selectedObject) {
                projectGraphNetwork.selectNodes([selectedObject]);
            } else {
                projectGraphNetwork.unselectAll();
            }
        }
    }

    function destroyProjectKnowledgeGraph() {
        if (projectGraphNetwork) {
            projectGraphNetwork.destroy();
            projectGraphNetwork = null;
        }

        projectGraphNodes = null;
        projectGraphEdges = null;

        if (projectKnowledgeGraph) {
            projectKnowledgeGraph.innerHTML = '';
            projectKnowledgeGraph.style.display = 'none';
        }

        if (projectGraphTitle) {
            projectGraphTitle.style.display = 'none';
        }
    }

    function renderProjectKnowledgeGraph(graphData, selectedObject = '') {
        if (!projectKnowledgeGraph) return;

        if (!window.vis) {
            projectKnowledgeGraph.style.display = 'block';
            projectKnowledgeGraph.innerHTML = '<div class="error">vis-network wurde nicht geladen.</div>';
            return;
        }

        if (!graphData || !Array.isArray(graphData.nodes) || graphData.nodes.length === 0) {
            destroyProjectKnowledgeGraph();
            projectKnowledgeGraph.style.display = 'block';
            projectKnowledgeGraph.innerHTML = '<div class="error">Keine verknüpften Objekte gefunden.</div>';
            return;
        }

        destroyProjectKnowledgeGraph();

        projectGraphDataCache = graphData;

        projectGraphNodes = new vis.DataSet((graphData.nodes || []).map(n => {
            const isSelected = Boolean(n.is_selected) || (selectedObject && n.id === selectedObject);

            return {
                id: n.id,
                label: n.label || n.id,
                title: n.title || n.label || n.id,
                shape: 'dot',
                size: isSelected ? 24 : 18,
                borderWidth: isSelected ? 4 : 2,
                color: {
                    background: '#ffffff',
                    border: isSelected ? '#00FFCC' : '#262626',
                    highlight: { background: '#ffffff', border: isSelected ? '#00FFCC' : '#262626' },
                    hover: { background: '#ffffff', border: isSelected ? '#00FFCC' : '#262626' }
                },
                font: {
                    color: '#262626'
                }
            };
        }));

        projectGraphEdges = new vis.DataSet((graphData.edges || []).map((e, index) => ({
            id: e.id || `${e.from}__${e.to}__${e.label || 'related_to'}__${index}`,
            from: e.from,
            to: e.to,
            label: '',
            title: e.title || e.label || '',
            event_names: Array.isArray(e.event_names) ? e.event_names : [],
            arrows: {
                to: {
                    enabled: true,
                    type: 'triangle',
                    scaleFactor: 0.55
                }
            },
            smooth: {
                type: 'dynamic'
            },
            width: 1.2,
            color: {
                color: '#262626',
                highlight: '#262626',
                hover: '#262626',
                inherit: false
            },
            font: {
                align: 'middle',
                color: '#262626',
                size: 12
            }
        })));

        const options = {
            interaction: {
                hover: true,
                tooltipDelay: 120,
                navigationButtons: false,
                keyboard: true,
                dragNodes: true,
                dragView: true,
                zoomView: true
            },
            layout: {
                improvedLayout: true,
                randomSeed: 7
            },
            physics: {
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: -85,
                    centralGravity: 0.015,
                    springLength: 190,
                    springConstant: 0.05,
                    damping: 0.7,
                    avoidOverlap: 1
                },
                stabilization: {
                    enabled: true,
                    iterations: 250,
                    updateInterval: 25
                }
            },
            nodes: {
                shape: 'dot',
                scaling: {
                    min: 16,
                    max: 28
                },
                font: {
                    size: 18
                }
            }
        };

        projectGraphNetwork = new vis.Network(
            projectKnowledgeGraph,
            { nodes: projectGraphNodes, edges: projectGraphEdges },
            options
        );

        projectGraphNetwork.on('click', function(params) {
            if (params.nodes && params.nodes.length > 0) {
                showGraphConnectionInfoForNode(params.nodes[0]);
                return;
            }

            clearGraphConnectionInfo();
        });

        if (projectGraphTitle) {
            projectGraphTitle.style.display = 'block';
        }

        projectKnowledgeGraph.style.display = 'block';
        updateProjectKnowledgeGraphSelection(selectedObject);
    }

    async function refreshProjectKnowledgeGraph(selectedObject = '', forceReload = false) {
        const projectDir = projectDirInput.value.trim();
        const effectiveSelection = selectedObject || objectSelect.value || '';

        if (!projectDir) {
            destroyProjectKnowledgeGraph();
            clearGraphConnectionInfo();
            return;
        }

        if (!forceReload && projectGraphDataCache) {
            updateProjectKnowledgeGraphSelection(effectiveSelection);
            return;
        }

        if (projectGraphTitle) {
            projectGraphTitle.style.display = 'block';
        }
        projectKnowledgeGraph.innerHTML = '<p style="padding:12px;">KNOWLEDGE GRAPH WILL BE UPDATED ...</p>';

        try {
            const res = await fetch('/project-knowledge-graph', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_dir: projectDir,
                    object_name: effectiveSelection
                })
            });

            const data = await res.json();

            if (data.error) {
                throw new Error(data.error);
            }

            projectGraphDataCache = data;
            renderProjectKnowledgeGraph(projectGraphDataCache, effectiveSelection);
        } catch (error) {
            console.error("Error while loading knowledge graph:", error);
            projectKnowledgeGraph.innerHTML = `<div class="error">Fehler beim Laden des Wissensgraphen: ${escapeHtml(error.message || "Unbekannter Fehler")}</div>`;
        }
    }

    function loadEventContent(filename, activeButton) {
        const projectDir = projectDirInput.value.trim();
        const objectName = objectSelect.value;

        fetch('/event-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_dir: projectDir,
                object_name: objectName,
                filename: filename
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage("Fehler: " + data.error, 'error');
                return;
            }

            currentEventFilename = data.filename;
            selectedEventName.textContent = data.filename;
            eventEditor.value = data.content || '';
            eventEditorContainer.style.display = 'block';

            document.querySelectorAll('.event-button').forEach(btn => {
                btn.classList.remove('active');
            });

            if (activeButton) {
                activeButton.classList.add('active');
            }
        })
        .catch(error => {
            console.error("Error while loading event content:", error);
            showError("An error occurred while loading the event content.");
        });
    }
    
    saveEventBtn.addEventListener('click', async function() {
        const projectDir = projectDirInput.value.trim();
        const objectName = objectSelect.value;
        const content = eventEditor.value;

        if (!projectDir || !objectName || !currentEventFilename) {
            showError("No event selected.");
            return;
        }

        try {
            const res = await fetch('/save-event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_dir: projectDir,
                    object_name: objectName,
                    filename: currentEventFilename,
                    content: content
                })
            });

            const data = await res.json();

            if (data.error) {
                showMessage("Fehler: " + data.error, 'error');
                return;
            }

            showMessage("Saved successfully: " + currentEventFilename, 'success', 2500);
            projectGraphDataCache = null;
            await refreshProjectKnowledgeGraph(objectName, true);
        } catch (error) {
            console.error("Error while saving event content:", error);
            showError("An error occurred while saving the event.");
        }
    });

    function escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function inlineFormat(text) {
        let t = escapeHtml(text);

        t = t.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

        t = t.replace(/`([^`]+)`/g, function(_, value) {
            const trimmed = value.trim();

            if (/^[A-Za-z]+_\d+\.gml$/i.test(trimmed)) {
                return `<button type="button" class="event-ref-link" data-event-filename="${trimmed}"><code>${trimmed}</code></button>`;
            }

            return `<code>${trimmed}</code>`;
        });

        t = t.replace(
            /\b(obj_[A-Za-z0-9_]+|spr_[A-Za-z0-9_]+|snd_[A-Za-z0-9_]+|rm_[A-Za-z0-9_]+|scr_[A-Za-z0-9_]+|o_[A-Za-z0-9_]+)\b/g,
            '<code>$1</code>'
        );

        return t;
    }

    function attachEventReferenceHandlers(container) {
        const links = container.querySelectorAll('.event-ref-link');

        links.forEach(link => {
            if (link.dataset.bound === 'true') return;
            link.dataset.bound = 'true';

            link.addEventListener('click', () => {
                const filename = link.dataset.eventFilename;
                if (!filename) return;

                const matchingButton = eventButtonsContainer.querySelector(`[data-filename="${filename}"]`);

                loadEventContent(filename, matchingButton || null);

                if (objectEventsContainer.style.display === 'none') {
                    objectEventsContainer.style.display = 'block';
                }

                eventEditorContainer.style.display = 'block';
                eventEditor.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
        });
    }

    function attachChatEnhancements(container) {
        attachCopyHandlers(container);
        attachEventReferenceHandlers(container);
    }

    function renderMarkdown(text) {
        if (!text) return "";

        let input = text.split('\\r\\n').join('\\n');

        const codeBlocks = [];

        function buildCodeBlockHtml(code, lang = '') {
            const escapedCode = escapeHtml(code.replace(/^\\n+|\\n+$/g, ''));
            const escapedLang = escapeHtml(lang || '');

            return `
                <div class="codeblock-wrapper">
                    <div class="codeblock-toolbar">
                        <span class="codeblock-language">${escapedLang}</span>
                        <button class="copy-code-btn" type="button" title="Code kopieren" aria-label="Code kopieren">
                            <img src="/static/icons/copy.svg" alt="Code kopieren">
                        </button>
                    </div>
                    <pre><code>${escapedCode}</code></pre>
                </div>
            `;
        }

        input = input.replace(/```([a-zA-Z0-9_+-]*)\\n?([\\s\\S]*?)```/g, function(match, lang, code) {
            const token = `__CODEBLOCK_${codeBlocks.length}__`;
            codeBlocks.push(buildCodeBlockHtml(code, lang));
            return token;
        });

        const openFenceMatch = input.match(/```([a-zA-Z0-9_+-]*)\\n?([\\s\\S]*)$/);
        if (openFenceMatch) {
            const token = `__CODEBLOCK_${codeBlocks.length}__`;
            const lang = openFenceMatch[1] || '';
            const code = openFenceMatch[2] || '';
            codeBlocks.push(buildCodeBlockHtml(code, lang));
            input = input.replace(/```([a-zA-Z0-9_+-]*)\\n?([\\s\\S]*)$/, token);
        }

        const lines = input.split('\\n');
        let html = '';
        let inList = false;
        let inTable = false;

        function closeListIfNeeded() {
            if (inList) {
                html += '</ul>';
                inList = false;
            }
        }

        function closeTableIfNeeded() {
            if (inTable) {
                html += '</tbody></table>';
                inTable = false;
            }
        }

        function closeOpenBlocks() {
            closeListIfNeeded();
            closeTableIfNeeded();
        }

        function isMarkdownTableSeparator(line) {
            return /^\\|?(\\s*:?-{3,}:?\\s*\\|)+\\s*:?-{3,}:?\\s*\\|?$/.test(line);
        }

        function isMarkdownTableRow(line) {
            return /^\\|?.*\\|.*\\|?$/.test(line);
        }

        function parseTableRow(line) {
            return line
                .trim()
                .replace(/^\\|/, '')
                .replace(/\\|$/, '')
                .split('|')
                .map(cell => inlineFormat(cell.trim()));
        }

        for (let i = 0; i < lines.length; i++) {
            const rawLine = lines[i];
            const line = rawLine.trim();
            const nextLine = i + 1 < lines.length ? lines[i + 1].trim() : '';

            if (!line) {
                closeOpenBlocks();
                continue;
            }

            if (/^__CODEBLOCK_\\d+__$/.test(line)) {
                closeOpenBlocks();
                html += line;
                continue;
            }

            if (isMarkdownTableRow(line) && isMarkdownTableSeparator(nextLine)) {
                closeOpenBlocks();

                const headerCells = parseTableRow(rawLine);
                html += '<table class="chat-table"><thead><tr>';
                headerCells.forEach(cell => {
                    html += `<th>${cell}</th>`;
                });
                html += '</tr></thead><tbody>';

                inTable = true;
                i += 1;
                continue;
            }

            if (inTable) {
                if (isMarkdownTableRow(line) && !isMarkdownTableSeparator(line)) {
                    const rowCells = parseTableRow(rawLine);
                    html += '<tr>';
                    rowCells.forEach(cell => {
                        html += `<td>${cell}</td>`;
                    });
                    html += '</tr>';
                    continue;
                } else {
                    closeTableIfNeeded();
                }
            }

            if (/^####\\s+/.test(line)) {
                closeOpenBlocks();
                html += `<h5>${inlineFormat(line.replace(/^####\\s+/, ''))}</h5>`;
                continue;
            }

            if (/^###\\s+/.test(line)) {
                closeOpenBlocks();
                html += `<h4>${inlineFormat(line.replace(/^###\\s+/, ''))}</h4>`;
                continue;
            }

            if (/^##\\s+/.test(line)) {
                closeOpenBlocks();
                html += `<h3>${inlineFormat(line.replace(/^##\\s+/, ''))}</h3>`;
                continue;
            }

            if (/^#\\s+/.test(line)) {
                closeOpenBlocks();
                html += `<h3>${inlineFormat(line.replace(/^#\\s+/, ''))}</h3>`;
                continue;
            }

            if (/^---+$/.test(line)) {
                closeOpenBlocks();
                html += '<hr>';
                continue;
            }

            if (/^(\\*|-)\\s+/.test(line)) {
                closeTableIfNeeded();
                if (!inList) {
                    html += '<ul>';
                    inList = true;
                }
                html += `<li>${inlineFormat(line.replace(/^(\\*|-)\\s+/, ''))}</li>`;
                continue;
            }

            closeOpenBlocks();
            html += `<p>${inlineFormat(rawLine)}</p>`;
        }

        closeOpenBlocks();

        html = html.replace(/__CODEBLOCK_(\\d+)__/g, (_, idx) => codeBlocks[Number(idx)]);
        return html;
    }

    function createChatMessage(role, labelText) {
        const msg = document.createElement('div');
        msg.className = `chat-message ${role}`;

        const label = document.createElement('span');
        label.className = 'chat-label';
        label.textContent = labelText;

        const body = document.createElement('div');
        body.className = 'chat-body';

        msg.appendChild(label);
        msg.appendChild(body);
        chatOutput.appendChild(msg);
        chatOutput.scrollTop = chatOutput.scrollHeight;

        return { msg, body };
    }

    function appendUserMessage(text) {
        const parts = createChatMessage('user', 'DU:');
        parts.body.textContent = text;
        chatOutput.scrollTop = chatOutput.scrollHeight;
    }

    function appendAssistantMessageFormatted(text) {
        const parts = createChatMessage('assistant', 'GAMMA:');
        parts.body.innerHTML = renderMarkdown(text);
        attachChatEnhancements(parts.body);
        chatOutput.scrollTop = chatOutput.scrollHeight;
    }

    function addLoadingMessage() {
        const parts = createChatMessage('assistant', 'GAMMA:');
        parts.body.innerHTML = `
            <div class="chat-loading">
                <div class="spinner"></div>
                <div>Antwort wird erstellt ...</div>
            </div>
        `;
        return parts.msg;
    }

    function removeLoadingMessage(node) {
        if (node && node.parentNode) {
            node.parentNode.removeChild(node);
        }
    }

    async function typewriterAssistantMessage(text, speed = 20) {
        const parts = createChatMessage('assistant', 'GAMMA:');
        const raw = text || '';
        const cursor = '<span class="typing-cursor">|</span>';

        let current = '';

        for (let i = 0; i < raw.length; i++) {
            current += raw[i];
            parts.body.innerHTML = renderMarkdown(current) + cursor;
            attachChatEnhancements(parts.body);
            chatOutput.scrollTop = chatOutput.scrollHeight;
            await new Promise(resolve => setTimeout(resolve, speed));
        }

        parts.body.innerHTML = renderMarkdown(raw);
        attachChatEnhancements(parts.body);
        chatOutput.scrollTop = chatOutput.scrollHeight;
    }

    function attachCopyHandlers(container) {
        const copyButtons = container.querySelectorAll('.copy-code-btn');

        copyButtons.forEach(btn => {
            if (btn.dataset.bound === 'true') return;
            btn.dataset.bound = 'true';

            btn.addEventListener('click', async () => {
                const code = btn.closest('.codeblock-wrapper')?.querySelector('pre code')?.innerText || '';
                if (!code) return;

                try {
                    await navigator.clipboard.writeText(code);
                    btn.classList.add('copied');
                    setTimeout(() => btn.classList.remove('copied'), 1200);
                } catch (err) {
                    console.error('Copy failed:', err);
                    showError('Code konnte nicht kopiert werden.');
                }
            });
        });
    }

    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatBtn.click();
        }
    });

    sendChatBtn.addEventListener('click', async function() {
        const projectDir = projectDirInput.value.trim();
        const objectName = objectSelect.value || "";
        const message = chatInput.value.trim();

        if (!projectDir) {
            showError("Please enter a project directory first.");
            return;
        }

        if (!message) {
            showError("Please enter a chat message.");
            return;
        }

        appendUserMessage(message);
        chatInput.value = '';

        sendChatBtn.classList.add('send-disabled');
        sendChatBtn.disabled = true;
        chatInput.disabled = true;

        const loadingNode = addLoadingMessage();

        try {
            const res = await fetch('/project-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_dir: projectDir,
                    object_name: objectName,
                    message: message
                })
            });

            const data = await res.json();
            removeLoadingMessage(loadingNode);

            if (data.error) {
                showError(data.error);
                await typewriterAssistantMessage("Fehler: " + data.error, 8);
                return;
            }

            await typewriterAssistantMessage(data.answer || 'Keine Antwort erhalten.', 6);

        } catch (error) {
            console.error("Error while sending chat message:", error);
            removeLoadingMessage(loadingNode);
            showError("An error occurred while sending the chat request.");
            await typewriterAssistantMessage("Fehler beim Senden der Anfrage.", 8);
        } finally {
            sendChatBtn.classList.remove('send-disabled');
            sendChatBtn.disabled = false;
            chatInput.disabled = false;
            chatInput.focus();
        }
    });
});
"""

@app.route('/')
def index():
    return Response(HTML_CONTENT, mimetype='text/html')

@app.route('/styles.css')
def styles():
    return Response(CSS_CONTENT, mimetype='text/css')

@app.route('/script.js')
def script():
    return Response(JS_CONTENT, mimetype='application/javascript')

if __name__ == "__main__":
    app.run(debug=True)