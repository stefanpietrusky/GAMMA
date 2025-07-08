"""
title: GAMMA V1 [GAME AUTOMATED MECHANICS MODIFICATION & ADAPTATION]
author: stefanpietrusky
author_url: https://downchurch.studio/
version: 1.0
"""

import os, re, subprocess, shutil, textwrap
from flask import Flask, request, jsonify, Response
from openai import OpenAI

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

@app.route('/models', methods=['GET'])
def list_models():
    try:
        res = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True
        )
        lines = res.stdout.splitlines()
        models = []
        for line in lines:
            line = line.strip()
            if not line or line.lower().startswith(("name","tag","model","size")):
                continue
            name = re.split(r"\s+", line)[0]
            models.append(name)
    except Exception as e:
        print("Error when retrieving the Ollama models:", e)
        models = []
    return jsonify(models)

def run_ollama(prompt, model="llama3.2"):
    try:
        process = subprocess.Popen(
            ["ollama", "run", model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        stdout, stderr = process.communicate(input=f"{prompt}\n", timeout=60)
        if process.returncode != 0:
            return f"Error: {stderr.strip()}"
        return stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def call_gemini(prompt: str, model: str = "gemini-2.5-pro") -> str:
    exe = shutil.which("gemini") or shutil.which("gemini.cmd")
    if not exe:
        raise RuntimeError("Gemini-CLI not in PATH – `npm i -g @google/gemini-cli`?")

    p = textwrap.dedent(prompt).strip().replace("\n", " ")

    try:
        res = subprocess.run(
            [exe, "-p", p, "-m", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            stdin=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        msg = e.stderr.strip() or "(no details)"
        raise RuntimeError(f"Gemini CLI error (exit {e.returncode}):\n{msg}")

    out = res.stdout.strip()
    if not out:
        err = res.stderr.strip() or "(no output from Gemini)"
        raise RuntimeError(f"Gemini-CLI did not provide an answert:\n{err}")

    return out

@app.route('/generate-gml', methods=['POST'])
def generate_gml():
    project_dir = request.form.get("project_dir", "").strip()
    object_name = request.form.get("object_name", "").strip()
    topic = request.form.get("topic", "").strip()
    difficulty = request.form.get("difficulty", "middle").strip()
    backend = request.form.get("backend", "ollama")
    api_key = request.form.get("api_key", "").strip()
    gemini_model = request.form.get("gemini_model", "gemini-2.5-pro")
    ollama_model = request.form.get("ollama_model", "llama3.2")

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

    if backend == "openai":
        try:
            client = OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=800
            )

            gml_code = response.choices[0].message.content.strip()
            m = re.search(
                r"(question\s*=\s*\[\];.*?soundwrong\s*=\s*-1;)",
                gml_code,
                flags=re.DOTALL
            )
            if m:
                gml_code = m.group(1)
            else:
                app.logger.warning("LLM response does not contain an expected GML segment.")

        except Exception as e:
            return jsonify({"error": f"OpenAI-Error: {e}"}), 500

    elif backend == "gemini":
        try:
            gml_code = call_gemini(prompt, gemini_model)
            app.logger.debug("Gemini-RAW:\n%s", gml_code)
        except Exception as e:
            return jsonify({"error": f"Gemini-Error: {e}"}), 500
       
        m = re.search(
            r"(question\s*=\s*\[\];.*?soundwrong\s*=\s*-1;)",
            gml_code,
            flags=re.DOTALL
        )
        if m:
            gml_code = m.group(1)
        else:
            app.logger.warning("LLM response does not contain an expected GML segment.") 
          
    else: 
        gml_code = run_ollama(prompt, ollama_model)
        m = re.search(r"(question\s*=\s*\[\];.*?soundwrong\s*=\s*-1;)", gml_code, flags=re.DOTALL)
        if m:
            gml_code = m.group(1)
        else:
            app.logger.warning("LLM response does not contain an expected GML segment.")

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
    <title>GAMMA V1</title>
    <link rel="stylesheet" href="/styles.css">
</head>
<body>
    <div class="container">
        <h1>GAMMA V1</h1>
        
        <div class="video-config-row">
        <div class="video-config-item">
            <label for="backend-select">Backend:</label>
            <select id="backend-select">
            <option value="ollama">Local (Ollama)</option>
            <option value="openai">OpenAI API</option>
            <option value="gemini">Google Gemini CLI</option>
            </select>
        </div>
        <div class="video-config-item" id="ollama-model-div">
            <label for="ollama-model-select">Ollama-Model:</label>
            <select id="ollama-model-select">
            <option>load…</option>
            </select>
        </div>
        <div class="video-config-item" id="openai-key-div" style="display:none;">
            <label for="api-key-input">OpenAI-API-Key:</label>
            <input type="text" id="api-key-input" placeholder="sk-…" />
        </div>
        <div class="video-config-item" id="gemini-model-div" style="display:none;">
        <label for="gemini-model-select">Gemini-Model:</label>
        <select id="gemini-model-select">
            <option value="gemini-2.5-pro" selected>gemini-2.5-pro</option>
            <option value="gemini-2.5-flash">gemini-2.5-flash</option>
            <option value="gemini-1.5-pro-002">gemini-1.5-pro-002</option>
        </select>
        </div>
        </div>

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

        <div class="form-section">
        <label for="topic-input">Topic:</label>
        <input type="text" id="topic-input" placeholder="Enter your topic here...">
        </div>

        <div class="form-section difficulty-section">
        <label>Difficulty:</label>
        <div class="difficulty-buttons">
            <button class="difficulty-button" data-level="easy">Easy</button>
            <button class="difficulty-button selected" data-level="medium">Medium</button>
            <button class="difficulty-button" data-level="hard">Hard</button>
        </div>
        </div>

        <div class="form-section">
        <label for="file-input">Upload question file (optional):</label>
        <div id="drop-zone" class="drop-zone">
            <button type="button" id="action-btn">Search</button>
            <div id="file-name" class="file-name"></div>
            <input type="file" id="file-input" name="questions_file" hidden />
        </div>
        </div>

        <button id="generate-btn">Generate GML</button>

        <div id="spinner" class="spinner" style="display: none;"></div>

        <div id="result-container" class="result-container" style="display:none;">
            <h2>Generated GML code:</h2>
            <pre id="gml-output"></pre>
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
    max-width: 800px;
    margin: auto;
    background: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 0 10px rgba(0,0,0,0.1);
    border: 3px solid #262626;
}

h1, h2 {
    text-align: center;
    color: #333;
}

#topic-input {
    width: 100%;
    padding: 10px;
    border: 3px solid #262626;
    border-radius: 5px;
    box-sizing: border-box;
}

input[type="text"] {
    width: 100%;
    padding: 10px;
    border: 3px solid #262626;
    border-radius: 5px;
    box-sizing: border-box;
}

.difficulty-buttons {
    margin: 0;
    display: flex;
    gap: 10px; 
}

.difficulty-buttons .difficulty-button {
    font-size: 1rem;
    margin: 0;
}

.difficulty-section {
    margin: 10px 0;
}

.difficulty-button {
    padding: 10px 20px;
    border: 3px solid #262626;
    background-color: #ffffff;
    color: 262626;
    border-radius: 5px;
    cursor: pointer;
    transition: background-color 0.3s ease;
}

.difficulty-button.selected,
.difficulty-button:hover {
    background-color: #262626;
    border: 3px solid #262626;
    color: white;
}

.drop-zone {
    position: relative;
    border: 3px dashed #262626;
    border-radius: 5px;
    padding: 30px;
    text-align: center;
    cursor: pointer;
    background: #fafafa;
    transition: background .2s ease;
}

.drop-zone.dragover {
    background: #e0f7ff;
}

.drop-zone button {
    background: #ffffff;
    border: 3px solid #262626;
    border-radius: 5px;
    padding: 10px 10px;
    font-size: 1rem;
    cursor: pointer;
}

.drop-zone button:hover {
    background-color: #262626;
    border: 3px solid #262626;
    color: white;
    cursor: pointer;
}

.file-name {
    margin-top: 10px;
    color: #333;
    font-size: 0.9rem;
}

#generate-btn {
    padding: 10px;
    margin: 15px 0;
    border: 3px solid #262626;
    background-color: #ffffff;
    color: #262626;
    border-radius: 5px;
    cursor: pointer;
    font-size: 1em;
    transition: background-color 0.3s ease;
}

#generate-btn:hover {
    background-color: #262626;
    border: 3px solid #262626;
    color: white;
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

.spinner {
    border: 8px solid #262626;
    border-top: 8px solid #00B0F0;
    border-radius: 50%;
    width: 50px;
    height: 50px;
    animation: spin 1s linear infinite;
    margin: 20px auto;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.video-config-row {
    display: flex;
    gap: 15px;
    flex-wrap: wrap;  
    margin-top: 5px;
    margin-bottom: 5px;   
    justify-content: flex-start; 
}

.video-config-item {
    flex: 0 0 auto; 
    display: flex;
    flex-direction: column;
    min-width: 150px; 
    max-width: 240px; 
}

.video-config-item > label {
    margin-bottom: 5px;
    color: #262626;
    font-weight: 500;
}

.video-config-row,
.custom-file-container,
.form-section label,
#sentences + button,
#script-container {
    margin-bottom: 10px;
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
    border: 3px solid #00B0F0 !important;  
    box-shadow: 0 0 0 3px rgba(0, 176, 240, .35);
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

.fade-out {
  animation: fadeOut 0.5s ease-out forwards;
}

@keyframes fadeOut {
  to {
    opacity: 0;
  }
}

#clear-file-btn {
    margin-top: 5px;
    background: none;
    border: none;
    color: #f44336;
    cursor: pointer;
    font-size: 0.9em;
    text-decoration: underline;
}

.remove-btn {
    background-color: #ffffff !important;    
    border-color: #f44336 !important; 
    color: #f44336 !important; 
}

.remove-btn:hover {
    background-color: #f44336 !important; 
    border-color: #f44336 !important; 
}
"""

JS_CONTENT = """
document.addEventListener('DOMContentLoaded', function() {
    const generateBtn = document.getElementById('generate-btn');
    const topicInput = document.getElementById('topic-input');
    const resultContainer = document.getElementById('result-container');
    const gmlOutput = document.getElementById('gml-output');
    const spinner = document.getElementById('spinner');
    const backendSelect = document.getElementById('backend-select');
    const openaiKeyDiv = document.getElementById('openai-key-div');
    const openaiApiKeyInput = document.getElementById('api-key-input');
    const geminiModelDiv = document.getElementById('gemini-model-div');
    const ollamaModelDiv = document.getElementById('ollama-model-div');
    const ollamaModelSelect = document.getElementById('ollama-model-select');
    const projectDirInput = document.getElementById('project-dir-input');
    const objectSelect = document.getElementById('object-select');
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const actionBtn = document.getElementById('action-btn');
    const fileNameDiv = document.getElementById('file-name');

    dropZone.addEventListener('click', () => fileInput.click());

    ;['dragover','dragenter'].forEach(evt =>
    dropZone.addEventListener(evt, e => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    })
    );
    dropZone.addEventListener('dragleave', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    });
    dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    fileInput.files = e.dataTransfer.files;
    handleFileChange();
    });

    fileInput.addEventListener('change', handleFileChange);

    function handleFileChange() {
    const file = fileInput.files[0];
    if (file) {
        fileNameDiv.textContent = file.name;
        actionBtn.textContent = 'Remove';
        actionBtn.classList.add('remove-btn');
        actionBtn.onclick = removeFile;
        themaInput.disabled = true;
    } else {
        resetDropZone();
    }
    }

    function removeFile(e) {
    e.stopPropagation();
    fileInput.value = '';
    resetDropZone();
    }

    function resetDropZone() {
    fileNameDiv.textContent = '';
    actionBtn.textContent = 'Search';
    actionBtn.classList.remove('remove-btn');
    actionBtn.onclick = () => fileInput.click();
    themaInput.disabled = false;
    }

    projectDirInput.addEventListener('blur', () => {
    const projectDir = projectDirInput.value.trim();
    if (!projectDir) return;

    fetch('/list-objects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_dir: projectDir })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
        showError("Fehler: " + data.error);
        return;
        }
        objectSelect.innerHTML = '<option value="" disabled selected>Wähle einen Ordner…</option>';
        data.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        objectSelect.appendChild(opt);
        });
    })
    .catch(err => console.error(err));
    });

    fetch('/models')
    .then(res => res.json())
    .then(models => {
        ollamaModelSelect.innerHTML = models
        .map(m => `<option value="${m}">${m}</option>`)
        .join('');
    })
    .catch(() => {
        ollamaModelSelect.innerHTML = '<option value="">Loading error</option>';
    });
    backendSelect.dispatchEvent(new Event('change'));
    backendSelect.addEventListener('change', function () {
        openaiKeyDiv.style.display = backendSelect.value === 'openai' ? 'flex' : 'none';
        geminiModelDiv.style.display = backendSelect.value === 'gemini' ? 'flex' : 'none';
        ollamaModelDiv.style.display = backendSelect.value === 'ollama' ? 'flex' : 'none';
    });

    let selectedDifficulty = "Middle";
    const difficultyButtons = document.querySelectorAll('.difficulty-button');

    difficultyButtons.forEach(button => {
        button.addEventListener('click', function() {
            difficultyButtons.forEach(btn => btn.classList.remove('selected'));
            this.classList.add('selected');
            selectedDifficulty = this.getAttribute('data-level');
        });
    });

    generateBtn.addEventListener('click', function() {
        const topic = topicInput.value.trim();
        const projectDir = projectDirInput.value.trim();
        const objectName = objectSelect.value;

        if (!projectDir) {
            showError("Please enter the project directory.");
            return;
        }
        if (!fileInput.files[0] && !topic) {
            showError("Please enter a topic.");
            return;
        }

        const formData = new FormData();
        formData.append('project_dir', projectDir);
        formData.append('object_name', objectName);
        formData.append('topic', topic);
        formData.append('difficulty', selectedDifficulty);
        formData.append('backend', backendSelect.value);
        formData.append('api_key', openaiApiKeyInput.value.trim());
        formData.append('gemini_model', document.getElementById('gemini-model-select').value);
        formData.append('ollama_model', ollamaModelSelect.value);

        if (fileInput.files[0]) {
            formData.append('questions_file', fileInput.files[0]);
        }

        spinner.style.display = 'block';
        resultContainer.style.display = 'none';

        fetch('/generate-gml', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            spinner.style.display = 'none';
            if (data.error) {
                showError("Fehler: " + data.error);
            } else if (data.gml_code) {
                gmlOutput.textContent = data.gml_code;
                resultContainer.style.display = 'block';
            } else {
                showError("Upload was successful: " + data.status);
            }
        })
        .catch(error => {
            spinner.style.display = 'none';
            console.error("Error when retrieving the GML code:", error);
            showError("An error occurred when retrieving the GML code.");
        });
    });

    function showError(msg, timeout_ms = 5000) {
    const container = document.getElementById('message-container');
    if (!container) return;

    container.innerHTML = '';

    const alertDiv = document.createElement('div');
    alertDiv.classList.add('error');
    alertDiv.textContent = msg;
    container.appendChild(alertDiv);

    setTimeout(() => {
        alertDiv.classList.add('fade-out');
        alertDiv.addEventListener('animationend', () => {
        if (container.contains(alertDiv)) container.removeChild(alertDiv);
        }, { once: true });
    }, timeout_ms);
    }
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
