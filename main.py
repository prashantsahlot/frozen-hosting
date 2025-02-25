import os
import subprocess
import tempfile
import time
import threading
import uuid

from flask import Flask, request, jsonify, render_template_string, Response, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersekrit")  # Change for production!

# ------------------------------------------------------------------------------
# Global dictionaries for deployment state
# ------------------------------------------------------------------------------
build_logs = {}      # deployment_id -> list of log strings
build_status = {}    # deployment_id -> "running" or "complete"
build_result = {}    # deployment_id -> container_id (if success)

# Dictionary to map user (by IP address) to container ID
user_container = {}

# ------------------------------------------------------------------------------
# HTML Templates
# ------------------------------------------------------------------------------

# 1) Public Landing Page
LANDING_HTML = '''
<!doctype html>
<html>
  <head>
    <title>Frozen Bots - Revolution in Development</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css" />
    <style>
      body {
        margin: 0;
        padding: 0;
        background: linear-gradient(135deg, #0b0b0b 0%, #1c1c1c 100%);
        font-family: Arial, sans-serif;
        color: #e0e0e0;
      }
      .hero {
        text-align: center;
        padding: 80px 20px;
      }
      .hero h1 {
        color: #00bcd4;
        font-size: 3em;
        margin: 0;
        text-shadow: 0 0 10px #00bcd4;
      }
      .hero p {
        margin-top: 20px;
        line-height: 1.6;
        max-width: 700px;
        margin-left: auto;
        margin-right: auto;
      }
      .btn-primary {
        display: inline-block;
        margin-top: 40px;
        padding: 15px 30px;
        background: #00bcd4;
        color: #121212;
        font-weight: bold;
        border: none;
        border-radius: 4px;
        text-decoration: none;
        cursor: pointer;
      }
      .btn-primary:hover {
        background: #0097a7;
      }
      .features {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        padding: 40px 20px;
        max-width: 1000px;
        margin: 0 auto;
      }
      .feature {
        flex: 1 1 300px;
        background: #1e1e1e;
        margin: 10px;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
      }
      .feature i {
        font-size: 2em;
        color: #00bcd4;
        margin-bottom: 10px;
      }
      .feature h3 {
        margin-top: 0;
        margin-bottom: 10px;
      }
      .feature p {
        font-size: 0.95em;
        line-height: 1.4;
      }
    </style>
  </head>
  <body>
    <div class="hero animate__animated animate__fadeInDown">
      <h1>Frozen Bots</h1>
      <p>
        We are starting a revolution in app development and hosting.<br>
        Say goodbye to complicated deployment pipelines and obscure error logs.
        Frozen Bots is your one-stop solution for frictionless container-based hosting.
      </p>
      <p>
        Deploy your code with a single click, view real-time logs, manage environment variables easily,
        and watch your ideas come to life – all in one platform.
      </p>
      <a class="btn-primary animate__animated animate__pulse animate__infinite" href="{{ url_for('deploy_config') }}">
        Start Deploying
      </a>
    </div>
    <div class="features animate__animated animate__fadeInUp">
      <div class="feature">
        <i class="fas fa-rocket"></i>
        <h3>One-Click Deploy</h3>
        <p>Push your code to GitHub (or any Git repo) and deploy instantly with a single click.</p>
      </div>
      <div class="feature">
        <i class="fas fa-sync-alt"></i>
        <h3>Automated Builds</h3>
        <p>We automatically build and containerize your app inside a Docker container.</p>
      </div>
      <div class="feature">
        <i class="fas fa-stream"></i>
        <h3>Real-Time Logs</h3>
        <p>Monitor your container logs in real time, updated every second with auto scroll.</p>
      </div>
      <div class="feature">
        <i class="fas fa-shield-alt"></i>
        <h3>Secure & Reliable</h3>
        <p>Hosted on robust infrastructure with secure isolation for each container.</p>
      </div>
      <div class="feature">
        <i class="fas fa-code-branch"></i>
        <h3>Flexible Env Vars</h3>
        <p>Configure environment variables quickly – no restarts required.</p>
      </div>
      <div class="feature">
        <i class="fas fa-cogs"></i>
        <h3>Scalable Architecture</h3>
        <p>Scale your containers up or down in seconds to handle any traffic demands.</p>
      </div>
    </div>
  </body>
</html>
'''

# 2) Deployment Configuration Page
DEPLOY_CONFIG_HTML = '''
<!doctype html>
<html>
  <head>
    <title>Frozen Bots - Deploy Your App</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <style>
      body { background-color: #121212; color: #e0e0e0; font-family: Arial, sans-serif; margin: 0; padding: 0; }
      .header { text-align: center; padding: 20px; background-color: #1e1e1e; }
      .header h1 { color: #00bcd4; margin: 0; text-shadow: 0 0 10px #00bcd4; }
      .container { max-width: 600px; margin: 20px auto; background-color: #1e1e1e; padding: 20px; border-radius: 8px; }
      label { display: block; margin-bottom: 5px; }
      input, textarea { width: 100%; padding: 10px; margin-bottom: 15px; border: none; border-radius: 4px; background: #2e2e2e; color: #e0e0e0; }
      button { background: #00bcd4; color: #121212; padding: 10px; border: none; border-radius: 4px; cursor: pointer; width: 100%; }
      button:hover { background: #0097a7; }
      .instructions { font-size: 0.9em; color: #aaa; margin-bottom: 20px; }
      a { color: #00bcd4; text-decoration: none; }
    </style>
  </head>
  <body>
    <div class="header animate__animated animate__fadeInDown">
      <h1>Frozen Bots</h1>
      <p>Configure Your Deployment</p>
    </div>
    <div class="container animate__animated animate__fadeInUp">
      <div class="instructions">
        <p>Enter your Git repository URL. The container will clone the repository and run it.</p>
        <p>You may also provide a custom start command (defaults to <code>python bot.py</code>) and environment variables (one per line in the format <code>KEY=VALUE</code>).</p>
      </div>
      <form action="/deploy" method="post">
        <label for="repo_url">Repository URL:</label>
        <input type="text" id="repo_url" name="repo_url" placeholder="https://github.com/username/repo.git" required>
        
        <label for="start_command">Start Command (optional):</label>
        <input type="text" id="start_command" name="start_command" placeholder="python bot.py">
        
        <label for="extra_env">Environment Variables (optional):</label>
        <textarea id="extra_env" name="extra_env" rows="4" placeholder="DEBUG=true&#10;LOG_LEVEL=info"></textarea>
        
        <button type="submit">Start Deployment</button>
      </form>
      <br>
      <p>If you already have a container deployed, please <a href="{{ url_for('container_status') }}">view or remove it</a>.</p>
    </div>
  </body>
</html>
'''

# 3) Build Logs Page
BUILD_LOGS_HTML = '''
<!doctype html>
<html>
  <head>
    <title>Frozen Bots - Build Logs</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <style>
      body { background-color: #121212; color: #e0e0e0; font-family: monospace; margin: 0; padding: 20px; }
      .header { text-align: center; padding: 10px; }
      .header h1 { color: #00bcd4; text-shadow: 0 0 10px #00bcd4; }
      #log-container { background: #1e1e1e; border-radius: 8px; padding: 20px; height: 70vh; overflow-y: scroll; white-space: pre-wrap; }
      .spinner {
         border: 8px solid #2e2e2e;
         border-top: 8px solid #00bcd4;
         border-radius: 50%;
         width: 60px;
         height: 60px;
         animation: spin 1s linear infinite;
         margin: 20px auto;
      }
      @keyframes spin { 100% { transform: rotate(360deg); } }
      #loading { text-align: center; }
    </style>
  </head>
  <body>
    <div class="header animate__animated animate__fadeInDown">
      <h1>Frozen Bots</h1>
      <p>Build Logs</p>
    </div>
    <div id="log-container" class="animate__animated animate__fadeInUp"></div>
    <div id="loading">
      <div class="spinner"></div>
      <p>Building... Please wait.</p>
    </div>
    <script>
      var deploymentId = "{{ deployment_id }}";
      var logContainer = document.getElementById("log-container");
      var loadingDiv = document.getElementById("loading");
      function pollLogs() {
        fetch("/get_logs/" + deploymentId)
          .then(response => response.json())
          .then(data => {
            logContainer.innerHTML = data.logs.join("");
            logContainer.scrollTop = logContainer.scrollHeight;
            if(data.status === "complete" && data.container_id) {
              setTimeout(function(){
                window.location.href = "/live_logs/" + data.container_id;
              }, 1000);
            } else {
              setTimeout(pollLogs, 1000);
            }
          })
          .catch(err => {
            console.error("Error polling logs:", err);
            setTimeout(pollLogs, 1000);
          });
      }
      pollLogs();
    </script>
  </body>
</html>
'''

# 4) Live Container Logs Page
LIVE_LOGS_HTML = '''
<!doctype html>
<html>
  <head>
    <title>Frozen Bots - Live Container Logs</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <style>
      body { background-color: #121212; color: #e0e0e0; font-family: monospace; margin: 0; padding: 20px; }
      .header { text-align: center; padding: 10px; }
      .header h1 { color: #00bcd4; text-shadow: 0 0 10px #00bcd4; }
      #log-container { background: #1e1e1e; border-radius: 8px; padding: 20px; height: 70vh; overflow-y: scroll; white-space: pre-wrap; }
      .spinner {
         border: 8px solid #2e2e2e;
         border-top: 8px solid #00bcd4;
         border-radius: 50%;
         width: 60px;
         height: 60px;
         animation: spin 1s linear infinite;
         margin: 20px auto;
      }
      @keyframes spin { 100% { transform: rotate(360deg); } }
      #loading { text-align: center; }
    </style>
  </head>
  <body>
    <div class="header animate__animated animate__fadeInDown">
      <h1>Frozen Bots</h1>
      <p>Live Container Logs</p>
    </div>
    <div id="log-container" class="animate__animated animate__fadeInUp"></div>
    <div id="loading">
      <div class="spinner"></div>
      <p>Connecting to live logs...</p>
    </div>
    <script>
      var logContainer = document.getElementById("log-container");
      var loadingDiv = document.getElementById("loading");
      var eventSource = new EventSource("/logs_stream/{{ container_id }}");
      eventSource.onmessage = function(e) {
         if(loadingDiv.style.display !== "none") {
           loadingDiv.style.display = "none";
           logContainer.style.display = "block";
         }
         logContainer.innerHTML += e.data;
         logContainer.scrollTop = logContainer.scrollHeight;
      };
      eventSource.onerror = function() {
         console.error("Error connecting to live logs.");
      };
    </script>
  </body>
</html>
'''

# 5) Container Status / Removal Page
CONTAINER_STATUS_HTML = '''
<!doctype html>
<html>
  <head>
    <title>Frozen Bots - Your Container Status</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <style>
      body { background-color: #121212; color: #e0e0e0; font-family: Arial, sans-serif; margin: 0; padding: 20px; text-align: center; }
      .container { max-width: 600px; margin: 0 auto; padding: 20px; background-color: #1e1e1e; border-radius: 8px; }
      .btn { display: inline-block; padding: 10px 20px; background: #00bcd4; color: #121212; border: none; border-radius: 4px; text-decoration: none; margin: 10px; }
      .btn:hover { background: #0097a7; }
    </style>
  </head>
  <body>
    <div class="container animate__animated animate__fadeInDown">
      <h1>Your Container</h1>
      <p>You already have a container deployed with ID: <strong>{{ container_id }}</strong></p>
      <a class="btn" href="{{ url_for('live_logs', container_id=container_id) }}">View Live Logs</a>
      <a class="btn" href="{{ url_for('remove_container') }}">Remove My Container</a>
    </div>
  </body>
</html>
'''

# ------------------------------------------------------------------------------
# Deployment Build Process (Background Thread)
# ------------------------------------------------------------------------------

# Updated generate_dockerfile: clone the repo inside the container.
def generate_dockerfile(repo_url, start_command):
    return f'''FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
RUN git clone {repo_url} . 
RUN pip install --no-cache-dir -r requirements.txt
CMD ["sh", "-c", "{start_command}"]
'''

def build_deployment(deployment_id, form_data):
    build_logs[deployment_id] = []
    build_status[deployment_id] = "running"
    
    def log(msg):
        build_logs[deployment_id].append(msg)
    
    try:
        log("Starting deployment...\n\n")
        time.sleep(1)
        
        # Create a temporary working directory.
        work_dir = tempfile.mkdtemp(prefix="bot_deploy_")
        log(f"Created temporary directory: {work_dir}\n\n")
        time.sleep(1)
        
        # Get repo URL and start command.
        repo_url = form_data.get('repo_url')
        start_command = form_data.get('start_command', '').strip()
        if not start_command:
            start_command = "python bot.py"
        
        # Generate Dockerfile that clones the repository inside the container.
        dockerfile_content = generate_dockerfile(repo_url, start_command)
        dockerfile_path = os.path.join(work_dir, "Dockerfile")
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(dockerfile_content)
        log("Generated Dockerfile with in-container clone instructions.\n\n")
        time.sleep(1)
        
        # Build the Docker image.
        image_tag = f"user_app_image_{int(time.time())}"
        log(f"Building Docker image with tag {image_tag}...\n")
        build_proc = subprocess.Popen(
            ["docker", "build", "-t", image_tag, work_dir],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace"
        )
        build_logs_list = []
        for line in iter(build_proc.stdout.readline, ""):
            build_logs_list.append(line)
        build_proc.wait()
        for line in build_logs_list:
            log(line)
        if build_proc.returncode != 0:
            log("Error building Docker image. Return code: " + str(build_proc.returncode) + "\n")
            build_status[deployment_id] = "complete"
            return
        log("Docker image built successfully.\n\n")
        time.sleep(1)
        
        # Process environment variables.
        env_vars = []
        extra_env = form_data.get('extra_env', '')
        if extra_env:
            for line in extra_env.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars.extend(["-e", f"{key.strip()}={value.strip()}"])
        
        # Run the Docker container.
        log("Starting Docker container...\n")
        run_proc = subprocess.Popen(
            ["docker", "run", "-d"] + env_vars + [image_tag],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace"
        )
        container_output = run_proc.stdout.read()
        if container_output is None:
            container_output = ""
        container_id = container_output.strip()
        run_proc.wait()
        if run_proc.returncode != 0 or not container_id:
            log("Error running Docker container. Return code: " + str(run_proc.returncode) + "\n")
            build_status[deployment_id] = "complete"
            return
        log(f"Container started with ID: {container_id}\n\n")
        log("Deployment complete.\n")
        
        build_result[deployment_id] = container_id
        
    except Exception as e:
        log(f"Exception occurred: {str(e)}\n")
    build_status[deployment_id] = "complete"

# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.route('/')
def landing():
    return render_template_string(LANDING_HTML)

@app.route('/deploy_config')
def deploy_config():
    return render_template_string(DEPLOY_CONFIG_HTML)

@app.route('/deploy', methods=['POST'])
def deploy():
    user_ip = request.remote_addr
    if user_ip in user_container:
        return redirect(url_for('container_status'))
    
    form_data = {
        'repo_url': request.form.get('repo_url'),
        'start_command': request.form.get('start_command'),
        'extra_env': request.form.get('extra_env'),
    }
    deployment_id = uuid.uuid4().hex
    thread = threading.Thread(target=build_deployment, args=(deployment_id, form_data))
    thread.start()
    
    def assign_container():
        while build_status.get(deployment_id, "running") == "running":
            time.sleep(1)
        container_id = build_result.get(deployment_id, "")
        if container_id:
            user_container[user_ip] = container_id
    threading.Thread(target=assign_container).start()
    
    return render_template_string(BUILD_LOGS_HTML, deployment_id=deployment_id)

@app.route('/get_logs/<deployment_id>')
def get_logs(deployment_id):
    logs = build_logs.get(deployment_id, [])
    status = build_status.get(deployment_id, "running")
    container_id = build_result.get(deployment_id, "")
    return jsonify({"logs": logs, "status": status, "container_id": container_id})

@app.route('/live_logs/<container_id>')
def live_logs(container_id):
    return render_template_string(LIVE_LOGS_HTML, container_id=container_id)

@app.route('/logs_stream/<container_id>')
def logs_stream(container_id):
    def generate_logs():
        process = subprocess.Popen(
            ["docker", "logs", "-f", container_id],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace"
        )
        for line in iter(process.stdout.readline, ""):
            yield f"data: {line}\n\n"
    return Response(generate_logs(), mimetype='text/event-stream')

@app.route('/container_status')
def container_status():
    user_ip = request.remote_addr
    container_id = user_container.get(user_ip)
    if not container_id:
        return redirect(url_for('deploy_config'))
    return render_template_string(CONTAINER_STATUS_HTML, container_id=container_id)

@app.route('/remove_container')
def remove_container():
    user_ip = request.remote_addr
    container_id = user_container.get(user_ip)
    if container_id:
        subprocess.run(["docker", "stop", container_id])
        subprocess.run(["docker", "rm", container_id])
        user_container.pop(user_ip, None)
    return redirect(url_for('deploy_config'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
