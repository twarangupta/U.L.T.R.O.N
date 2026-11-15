"""Git commands for the repository ULTRON was started in (D30 registry)."""
import subprocess
from datetime import datetime

from ultron.commands.registry import Done, Param, command

_GROUP = "Git"
_GIT = r"(?:git|get)"  # Whisper often hears "get"


def _git(*args: str, capture: bool = True) -> str:
    res = subprocess.run(["git", *args], capture_output=capture, text=True, check=True)
    return (res.stdout or "").strip()


def _branch() -> str:
    return _git("branch", "--show-current")


@command("git_status", "Say how many files are modified or untracked in the git repo.", group=_GROUP,
         title="git status", priority=60,
         rules=[rf"(?:what s |what is |check |show )?(?:the |my )?{_GIT} status",
                r"(?:are there )?any (?:uncommitted|unsaved) changes"],
         examples=["git status", "what's the git status", "check git status", "do i have uncommitted changes",
                   "is my branch clean", "what files did i change", "anything modified in the repo"],
         not_examples=["what is my status at work", "check my order status"])
def git_status() -> str:
    lines = [line for line in _git("status", "--porcelain").split("\n") if line]
    if not lines:
        return "Your git branch is clean."
    return f"You have {len(lines)} untracked or modified files in your branch."


@command("git_commit", "Stage all changes and commit them, with the user's message if they gave one.",
         group=_GROUP, title="commit all changes", doing="Committing all changes.", priority=60,
         params=[Param("message", "str", "commit message, only if the user said one", required=False,
                       cues=("with message", "with the message", "message", "saying"))],
         rules=[rf"{_GIT} commit(?: (?:with )?(?:the )?message (?P<message>.+))?",
                rf"commit (?:my |all )?(?:the )?changes(?: (?:with )?(?:the )?message (?P<message>.+))?",
                rf"{_GIT} check in"],
         examples=["git commit", "commit my changes", "commit everything", "commit all changes",
                   "git commit with message fix the login bug", "save my work in git", "make a commit"],
         not_examples=["i can't commit to that", "what is a commit", "commit to a gym routine"])
def git_commit(message: str | None = None) -> str:
    msg = message or f"Automated commit via ULTRON on {datetime.now():%Y-%m-%d %H:%M:%S}"
    _git("add", ".", capture=False)
    _git("commit", "-m", msg, capture=False)
    return Done(f"Committed with message: {msg}.")


@command("git_push", "Push the current branch to origin.", group=_GROUP, title="push the current branch",
         doing="Pushing to origin.", priority=60,
         rules=[rf"{_GIT} push", r"push (?:my |the )?(?:changes|commits|code|branch)(?: to (?:github|origin|remote))?"],
         examples=["git push", "push my changes", "push the code to github", "push my commits",
                   "send my commits to the remote", "upload my changes to github"],
         not_examples=["push the button", "push yourself harder", "push notifications"])
def git_push() -> str:
    branch = _branch()
    if not branch:
        return "I couldn't identify the current active branch."
    _git("push", "origin", branch, capture=False)
    return Done(f"Pushed branch {branch} to origin.")


@command("git_pull", "Pull the latest changes of the current branch from origin.", group=_GROUP,
         title="pull the latest changes", priority=60,
         rules=[rf"{_GIT} pull", r"pull (?:the )?(?:latest )?(?:changes|code)(?: from (?:remote|origin|github))?",
                r"pull from (?:remote|origin)"],
         examples=["git pull", "pull the latest changes", "sync my repo with remote", "get the latest code",
                   "update my branch from github", "pull from origin"],
         not_examples=["pull an all nighter", "pull up youtube"])
def git_pull() -> str:
    branch = _branch()
    if not branch:
        return "I couldn't identify the current active branch."
    _git("pull", "origin", branch, capture=False)
    return f"Pulled the latest changes on branch {branch}."


@command("git_stash", "Stash the uncommitted changes.", group=_GROUP, title="stash my changes", priority=60,
         rules=[rf"{_GIT} stash", r"stash (?:my |the )?changes"],
         examples=["git stash", "stash my changes", "put my current work on hold", "shelve my changes",
                   "park my changes for now"])
def git_stash() -> str:
    _git("stash", capture=False)
    return "Stashed your local changes."


@command("git_stash_pop", "Bring back the most recent stash.", group=_GROUP, title="pop the stash", priority=61,
         rules=[rf"{_GIT} stash pop", r"(?:pop|apply|unstash) (?:the |my )?stash(?:ed changes)?"],
         examples=["git stash pop", "pop the stash", "bring back my stashed changes", "unstash my work",
                   "restore my stash"])
def git_stash_pop() -> str:
    _git("stash", "pop", capture=False)
    return "Popped the top stash."


@command("git_conflicts", "List files with merge conflicts.", group=_GROUP, title="check for merge conflicts",
         priority=60,
         rules=[rf"(?:{_GIT}|merge|any|check(?: for)?)(?: merge)? conflicts?"],
         examples=["any merge conflicts", "check for conflicts", "git conflicts", "which files have conflicts",
                   "did the merge break anything"])
def git_conflicts() -> str:
    files = [f for f in _git("diff", "--name-only", "--diff-filter=U").split("\n") if f.strip()]
    if not files:
        return "No active merge conflicts detected in your repository."
    return f"Merge conflicts in: {', '.join(files)}."


@command("git_log", "Read the last 5 commits.", group=_GROUP, title="show recent commits", priority=60,
         rules=[rf"{_GIT} (?:log|history)", r"show (?:me )?(?:my )?(?:recent |last )?commits"],
         examples=["git log", "show my recent commits", "what were my last commits", "show the commit history",
                   "what did i commit lately", "git history"],
         not_examples=["tell me the history of india", "what is a log", "i meant whey protein"])
def git_log() -> str:
    lines = [line for line in _git("log", "-n", "5", "--oneline").split("\n") if line.strip()]
    if not lines:
        return "No commit history found."
    return "Here are the last 5 commits: " + " ... ".join(lines)


_BRANCH_NAME = Param("name", "str", "the branch name", cues=("branch called", "branch named", "branch to", "branch",
                                                             "switch to", "checkout"))


@command("git_create_branch", "Create a new git branch and switch to it.", group=_GROUP,
         title="create branch {name}", params=[_BRANCH_NAME], priority=62,
         rules=[r"(?:create|make|start)(?: a)?(?: new)? branch(?: called| named)? (?P<name>.+)",
                r"new branch(?: called| named)? (?P<name>.+)"],
         examples=["create branch login fix", "make a new branch called dark mode", "new branch feature x",
                   "start a branch named cleanup"])
def git_create_branch(name: str) -> str:
    name = name.replace(" ", "-")
    _git("checkout", "-b", name, capture=False)
    return f"Created and switched to branch {name}."


@command("git_switch_branch", "Switch to an existing git branch.", group=_GROUP, title="switch to branch {name}",
         params=[_BRANCH_NAME], priority=62,
         rules=[r"(?:switch|change)(?: to)?(?: the)? branch(?: to)? (?P<name>.+)",
                r"(?:checkout|check out)(?: the)?(?: branch)? (?P<name>.+)",
                r"switch to (?:the )?(?P<name>\S+) branch"],
         examples=["switch branch to main", "checkout branch develop", "switch to the main branch",
                   "change branch to p1 fixes", "go to the develop branch"])
def git_switch_branch(name: str) -> str:
    name = name.replace(" ", "-")
    _git("checkout", name, capture=False)
    return f"Switched to branch {name}."


@command("git_branches", "List the local git branches and say which one is current.", group=_GROUP,
         title="list branches", priority=60,
         rules=[rf"{_GIT} branch(?:es)?", r"(?:show|list)(?: me)?(?: all)?(?: my| the)? branches",
                r"(?:which|what) branch am i on"],
         examples=["git branch", "list branches", "which branch am i on", "show me all branches",
                   "what branches do i have"])
def git_branches() -> str:
    branches = [b.strip() for b in _git("branch").split("\n") if b.strip()]
    if not branches:
        return "No branches found."
    current = [b[1:].strip() for b in branches if b.startswith("*")]
    others = [b for b in branches if not b.startswith("*")]
    text = f"You are on branch {current[0]}." if current else ""
    return text + (f" Other branches: {', '.join(others)}." if others else " There are no other local branches.")
