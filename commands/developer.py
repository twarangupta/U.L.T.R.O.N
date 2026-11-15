"""Developer helpers: clipboard tools, ports, docker, code search, LLM-written reports (D30 registry)."""
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime

from commands.registry import Done, Param, command

_GROUP = "Developer"


def ask_local_ai(prompt: str) -> str:
    """One standalone LLM call (imported late: brain connects to Ollama on import)."""
    try:
        from brain import ask_once
        return ask_once(prompt)
    except Exception as e:
        return f"Error querying local AI: {e}"


def _paste(text: str):
    import pyautogui
    import pyperclip
    pyautogui.FAILSAFE = False
    pyperclip.copy(text)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")


def _strip_fences(code: str) -> str:
    return re.sub(r"```[a-zA-Z]*", "", code).strip()


@command("debug_clipboard_error", "Explain the error or stack trace on the clipboard and suggest a fix.",
         group=_GROUP, title="debug the error on the clipboard", priority=55,
         rules=[r"(?:debug|analy[sz]e|explain) (?:this |the |my )?(?:crash|stack trace|error|traceback)"],
         examples=["debug this crash", "analyze this stack trace", "explain the error i copied",
                   "what's wrong with this traceback", "debug error", "help me fix the error on my clipboard"])
def debug_clipboard_error() -> str:
    import pyperclip
    trace = pyperclip.paste().strip()
    if not trace:
        return "Your clipboard is empty. Copy the error first."
    report = ask_local_ai("You are an expert debugger. Explain this error in under 200 words and give the exact "
                          f"code change that fixes it:\n\n{trace}")
    with open("debug_report.md", "w", encoding="utf-8") as f:
        f.write(f"# Debug Analysis - {datetime.now():%Y-%m-%d %H:%M:%S}\n\n{report}\n")
    pyperclip.copy(report)
    return "Analysed. The report is in debug_report.md and on your clipboard."


@command("audit_dependencies", "Check this project's Python and Node packages for outdated versions.",
         group=_GROUP, title="audit dependencies", priority=55,
         rules=[r"(?:audit|check)(?: my| the)? (?:dependencies|packages)"],
         examples=["audit my dependencies", "check dependencies", "are my packages out of date",
                   "any outdated packages", "check the project's packages"])
def audit_dependencies() -> str:
    reports = []
    if os.path.exists("requirements.txt"):
        res = subprocess.run(["pip", "list", "--outdated", "--format=json"], capture_output=True, text=True)
        try:
            if res.returncode == 0 and json.loads(res.stdout or "[]"):
                reports.append(f"{len(json.loads(res.stdout))} outdated Python packages found.")
        except ValueError:
            reports.append("Some Python packages are outdated.")
    if os.path.exists("package.json"):
        res = subprocess.run(["npm", "outdated"], shell=True, capture_output=True, text=True)
        if res.stdout.strip():
            reports.append("Outdated Node.js packages detected.")
    return " and ".join(reports) or "All your project dependencies appear to be up to date."


@command("api_request", "Send an HTTP GET or POST request and copy the response to the clipboard.",
         group=_GROUP, title="send a {method} request to {url}",
         params=[Param("method", "choice", "HTTP method", choices=("get", "post")),
                 Param("url", "str", "the URL", cues=("request to", "to"))],
         priority=55,
         rules=[r"send (?:a |an )?(?P<method>get|post) request to (?P<url>.+)"],
         examples=["send a get request to localhost 8000", "send a post request to api example com",
                   "make a get request to localhost colon 3000"])
def api_request(method: str, url: str) -> str:
    import pyperclip
    url = url.replace("slash", "/").replace("colon", ":").replace(" dot ", ".").replace(" ", "")
    if not url.startswith("http"):
        url = "http://" + url
    req = urllib.request.Request(url, method=method.upper(), headers={"User-Agent": "ULTRON"})
    if method == "post":
        data = pyperclip.paste().strip()
        try:
            json.loads(data)
        except ValueError:
            data = "{}"
        req.data = data.encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as response:
        body = response.read().decode("utf-8", errors="replace")
        pyperclip.copy(f"Status: {response.status}\nHeaders:\n{json.dumps(dict(response.headers), indent=2)}"
                       f"\n\nBody:\n{body}")
        return f"Status {response.status}. The response is on your clipboard."


@command("explain_file", "Explain a code file in the current folder.", group=_GROUP, title="explain {file}",
         params=[Param("file", "str", "file name, for example ultron.py", cues=("file", "code"))], priority=55,
         rules=[r"explain (?:the )?(?:code )?(?:file )?(?P<file>[\w.-]+\.\w+)", r"explain (?:code )?file (?P<file>[\w. -]+)"],
         examples=["explain the file ultron.py", "explain code file brain.py", "what does speaker.py do",
                   "explain file audio.py"])
def explain_file(file: str) -> str:
    file = file.replace(" dot ", ".").replace(" ", "")
    if not os.path.exists(file):
        return f"File {file} does not exist in the current directory."
    with open(file, encoding="utf-8", errors="ignore") as f:
        code = f.read()[:4000]
    return f"{file}: " + ask_local_ai(f"Explain the purpose and main parts of this file in a few sentences:\n\n{code}")


@command("container_logs", "Copy the last 20 log lines of a docker container to the clipboard.", group=_GROUP,
         title="get logs for container {container}",
         params=[Param("container", "str", "container name", cues=("logs for", "logs of", "logs"))], priority=55,
         rules=[r"(?:check |get |show )?(?:the )?container logs(?: for| of)? (?P<container>.+)"],
         examples=["check container logs for api", "container logs web", "get the logs of the db container"])
def container_logs(container: str) -> str:
    import pyperclip
    res = subprocess.run(["docker", "logs", "--tail", "20", container], capture_output=True, text=True)
    output = res.stdout + res.stderr
    if not output.strip():
        return f"No logs found, or container {container} is not running."
    pyperclip.copy(output)
    return f"The last 20 log lines of {container} are on your clipboard."


def _pid_on_port(port: int) -> str | None:
    res = subprocess.run(f"netstat -ano | findstr :{port}", shell=True, capture_output=True, text=True)
    lines = [line.split() for line in res.stdout.strip().split("\n") if line.strip()]
    return lines[0][-1] if lines else None


@command("check_port", "Say which process is listening on a port.", group=_GROUP, title="check port {port}",
         params=[Param("port", "int", "port number")], priority=56,
         rules=[r"(?:what s|what is|check|who is) (?:on |using )?port (?P<port>\d+)", r"check port (?P<port>\d+)"],
         examples=["what's on port 3000", "check port 8080", "who is using port 5000",
                   "is anything running on port 8000"])
def check_port(port: int) -> str:
    pid = _pid_on_port(port)
    return f"Process {pid} is listening on port {port}." if pid else f"No process is running on port {port}."


@command("kill_port", "Force-stop the process listening on a port.", group=_GROUP, title="kill the process on port {port}",
         params=[Param("port", "int", "port number")], risk="confirm",
         confirm_text="force-stop the process on that port", priority=57,
         rules=[r"(?:kill|free|stop|end) (?:the )?(?:process )?(?:on |using )?port (?P<port>\d+)"],
         examples=["kill port 3000", "kill the process on port 8080", "free up port 5000",
                   "stop whatever is using port 8000"])
def kill_port(port: int) -> str:
    pid = _pid_on_port(port)
    if not pid:
        return f"No process is running on port {port}."
    subprocess.run(f"taskkill /F /PID {pid}", shell=True, check=True)
    return f"Stopped process {pid} on port {port}."


@command("docker_status", "List the running docker containers.", group=_GROUP, title="docker status", priority=55,
         rules=[r"(?:check )?docker(?: status)?|(?:which|what) containers are running"],
         examples=["docker status", "check docker", "which containers are running", "is docker running anything"])
def docker_status() -> str:
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=True)
    except Exception:
        return "Failed to query Docker. Ensure Docker Desktop is running."
    names = [c for c in out.stdout.split("\n") if c.strip()]
    return f"Running containers: {', '.join(names)}." if names else "No docker containers are running."


@command("format_json", "Pretty-print the JSON on the clipboard.", group=_GROUP, title="format the JSON on the clipboard",
         priority=55, rules=[r"(?:format|prettify|pretty print|beautify) (?:the |my )?json"],
         examples=["format json", "prettify the json", "pretty print json", "clean up the json i copied"])
def format_json() -> str:
    import pyperclip
    try:
        pretty = json.dumps(json.loads(pyperclip.paste().strip()), indent=4)
    except ValueError as e:
        return f"The clipboard is not valid JSON: {e}"
    pyperclip.copy(pretty)
    return "JSON formatted and copied back to the clipboard."


_SKIP_DIRS = ("venv", ".venv", ".git", "__pycache__", "node_modules")


@command("search_codebase", "Search the code files in the current folder for a word.", group=_GROUP,
         title="search the codebase for {term}",
         params=[Param("term", "str", "the text to find", cues=("for",))], priority=56,
         rules=[r"search (?:the )?(?:codebase|code|project) for (?P<term>.+)", r"find (?P<term>.+) in (?:the |my )?code(?:base)?"],
         examples=["search codebase for speak", "search the code for wake word", "find logger in the code",
                   "where in the project is transcribe used"])
def search_codebase(term: str) -> str:
    matches = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for file in files:
            if file.endswith((".py", ".txt", ".json", ".md", ".sh", ".ps1")):
                try:
                    with open(os.path.join(root, file), encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if term in line.lower():
                                matches.append(f"{file} line {i}")
                                break
                except OSError:
                    pass
            if len(matches) >= 3:
                return f"Found matches in: {', '.join(matches)}."
    return f"Found matches in: {', '.join(matches)}." if matches else f"No matches found for {term}."


@command("boilerplate", "Write starter code for a technology and paste it at the cursor.", group=_GROUP,
         title="paste {tech} boilerplate",
         params=[Param("tech", "str", "what the starter code is for, for example fastapi or a flask app",
                       cues=("boilerplate for", "template for", "starter code for", "for"))], priority=55,
         rules=[r"(?:create |write )?(?:a )?(?:boilerplate|template|starter code) for (?P<tech>.+)",
                r"create (?:a )?(?P<tech>fastapi)(?: app| boilerplate)?", r"(?P<tech>fastapi) boilerplate"],
         examples=["create fastapi boilerplate", "boilerplate for a flask app", "create a boilerplate for react",
                   "write starter code for an express server"])
def boilerplate(tech: str) -> str:
    if tech == "fastapi":
        code = ('from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.get("/")\n'
                'def read_root():\n    return {"message": "Hello World"}\n')
    else:
        code = _strip_fences(ask_local_ai(f"Write minimal boilerplate code for: {tech}. Output only raw code."))
    _paste(code)
    return f"Pasted the {tech} boilerplate at your cursor."


@command("review_code", "Review the uncommitted git diff with the LLM and write code_review.md.", group=_GROUP,
         title="review my code", priority=55,
         rules=[r"review (?:my |the )?(?:code|changes|diff)|code review"],
         examples=["review my code", "code review", "review my changes", "look over my diff for bugs"])
def review_code() -> str:
    diff = subprocess.run(["git", "diff"], capture_output=True, text=True, check=True).stdout.strip()
    if not diff:
        return "No changes detected in git."
    review = ask_local_ai("Review this git diff for bugs, style and performance. Be brief.\n\n" + diff[:4000])
    with open("code_review.md", "w", encoding="utf-8") as f:
        f.write(f"# Code Review - {datetime.now():%Y-%m-%d %H:%M:%S}\n\n{review}\n")
    return "Reviewed. The report is in code_review.md."


@command("write_unit_test", "Generate a pytest file for a Python file in the current folder.", group=_GROUP,
         title="write tests for {file}",
         params=[Param("file", "str", "the Python file", cues=("for", "test for", "tests for"))], priority=55,
         rules=[r"(?:write|generate) (?:a )?(?:unit )?tests? (?:suite )?for (?P<file>[\w. -]+)"],
         examples=["write a unit test for memory.py", "generate tests for brain.py", "write a test for audio.py"])
def write_unit_test(file: str) -> str:
    file = file.replace(" dot ", ".").replace(" ", "")
    if not os.path.exists(file):
        return f"File {file} does not exist in the current directory."
    with open(file, encoding="utf-8", errors="ignore") as f:
        code = f.read()[:4000]
    tests = _strip_fences(ask_local_ai(f"Write a pytest test suite for this code. Output only Python.\n\n{code}"))
    with open(f"test_{os.path.basename(file)}", "w", encoding="utf-8") as f:
        f.write(tests)
    return f"Tests saved as test_{os.path.basename(file)}."


@command("start_project", "Open VS Code in the current folder and GitHub in the browser.", group=_GROUP,
         title="start the project workspace", priority=55,
         rules=[r"(?:start|launch|open) (?:my |the )?(?:project|workspace)(?: workspace)?"],
         examples=["start project", "launch my workspace", "open the project workspace", "set up my coding workspace"])
def start_project() -> str:
    subprocess.Popen("code .", shell=True)
    import webbrowser
    webbrowser.open("https://github.com")
    return Done("Project workspace launched.")
