"""
title: GAMMA V2 [GAME AUTOMATED MECHANICS MODIFICATION & ADAPTATION]
author: stefanpietrusky
author_url: https://downchurch.studio/
version: 2.0
"""

import os, re
import yaml
import requests
from datetime import datetime
from flask import Flask, request, jsonify, Response
from dotenv import load_dotenv

load_dotenv()

OLLAMA_CLOUD_MODEL = "qwen3.5:397b-cloud"
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
        out.write("// ======================================================\\n")
        out.write("// Combined GML code of all objects\\n")
        out.write(f"// Generated on: {datetime.now():%Y-%m-%d %H:%M:%S}\\n")
        out.write(f"// Project: {project_dir}\\n")
        out.write("// ======================================================\\n\\n")

        for obj in sorted(obj_events):
            out.write(f"// === Object: {obj} ===\\n\\n")
            for event in sorted(obj_events[obj]):
                out.write(f"// --- Event: {event} ---\\n")
                for path, ext in sorted(obj_events[obj][event], key=lambda x: x[0]):
                    out.write(f"// File: {os.path.basename(path)}\\n")
                    if ext == ".gml":
                        with open(path, "r", encoding="utf-8") as f:
                            out.write(f.read().rstrip() + "\\n\\n")
                    else:
                        with open(path, "r", encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}
                        code = data.get("gml", "")
                        out.write(code.rstrip() + "\\n\\n")

            out.write("\\n")

        out.write("// === End of all objects ===\\n")

    return output_file


def read_combined_summary() -> str:
    summary_path = os.path.join(APP_DIR, COMBINED_CODE_FILENAME)
    if not os.path.isfile(summary_path):
        return ""
    with open(summary_path, "r", encoding="utf-8") as f:
        return f.read()

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

        return jsonify({
            "status": "Event file successfully saved",
            "path": file_path
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

@app.route('/generate-gml', methods=['POST'])
def generate_gml():
    project_dir = request.form.get("project_dir", "").strip()
    object_name = request.form.get("object_name", "").strip()
    topic = request.form.get("topic", "").strip()
    difficulty = request.form.get("difficulty", "medium").strip()

    if not project_dir or not object_name:
        return jsonify({"error": "Project directory and object folder must be specified."}), 400

    gml_path = os.path.join(project_dir, "objects", object_name, "Create_0.gml")
    if not os.path.isfile(gml_path):
        return jsonify({"error": f"File not found: {gml_path}"}), 404

    uploaded = request.files.get('questions_file')
    if uploaded:
        try:
            raw = uploaded.read().decode('utf-8')
            lines = raw.splitlines()
            cleaned = "\n".join([line for line in lines if line.strip() != ""])
            with open(gml_path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            return jsonify({
                "status": "File successfully uploaded and GML overwritten",
                "path": gml_path
            })
        except Exception as e:
            return jsonify({"error": f"Error saving the file: {e}"}), 500

    if not topic:
        return jsonify({"error": "Please enter a topic."}), 400

    prompt = f"""
    Create 3 multiple-choice questions on the topic:  {topic} with difficulty level: {difficulty}.
    Please return the output exactly in the following GML format (without additional comments or formatting):

    questions = [];
    questions[0] = "[Question 1]";
    questions[1] = "[Question 2]";
    questions[2] = "[Question 3]";

    answers = [];
    answers[0] = ["[Answer 1-1]", "[Answer 1-2]", "[Answer 1-3]"];
    answers[1] = ["[Answer 2-1]", "[Answer 2-2]", "[Answer 2-3]"];
    answers[2] = ["[Answer 3-1]", "[Answer 3-2]", "[Answer 3-3]"];

    currentQuestion = 0;

    correctAnswer = [];
    correctAnswer[0] = Index of the correct answer for question 1;
    correctAnswer[1] = Index of the correct answer for question 2;
    correctAnswer[2] = Index of the correct answer for question 3;

    soundright = -1;
    soundwrong = -1;

    Please replace all placeholders ([Question X] and [Answer X-Y]) with suitable, correct information.
    Important: When specifying the correct answer, you should **not** use square brackets - only the numerical index (as a number) must be used.
    Answer **only** with the GML code without introduction, without ```` blocks.
    """

    try:
        gml_code = call_ollama_cloud(prompt)

        m = re.search(
            r"(questions\s*=\s*\[\];.*?soundwrong\s*=\s*-1;)",
            gml_code,
            flags=re.DOTALL
        )
        if m:
            gml_code = m.group(1)
        else:
            app.logger.warning("LLM response does not contain an expected GML segment.")

    except Exception as e:
        return jsonify({"error": f"Ollama-Cloud-Error: {e}"}), 500


    try:
        with open(gml_path, "w", encoding="utf-8") as f:
            f.write(gml_code)
        return jsonify({
            "status": "GML file successfully created/overwritten",
            "path": gml_path,
            "gml_code": gml_code
        })
    except Exception as e:
        return jsonify({"error": f"Error while writing the file: {e}"}), 500

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GAMMA</title>
    <link rel="stylesheet" href="/styles.css">
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

    const chatOutput = document.getElementById('chat-output');
    const chatInput = document.getElementById('chat-input');
    const sendChatBtn = document.getElementById('send-chat-btn');

    let currentEventFilename = "";

    projectDirInput.addEventListener('blur', async () => {
        const projectDir = projectDirInput.value.trim();
        if (!projectDir) return;

        try {
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

        if (!projectDir || !objectName) {
            objectEventsContainer.style.display = 'none';
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
    saveEventBtn.addEventListener('click', function() {
        const projectDir = projectDirInput.value.trim();
        const objectName = objectSelect.value;
        const content = eventEditor.value;

        if (!projectDir || !objectName || !currentEventFilename) {
            showError("No event selected.");
            return;
        }

        fetch('/save-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_dir: projectDir,
                object_name: objectName,
                filename: currentEventFilename,
                content: content
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showMessage("Fehler: " + data.error, 'error');
                return;
            }

            showMessage("Saved successfully: " + currentEventFilename, 'success', 2500);
        })
        .catch(error => {
            console.error("Error while saving event content:", error);
            showError("An error occurred while saving the event.");
        });
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