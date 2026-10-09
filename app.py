import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, url_for

from github_client import GitHubAppClient, GitHubAppConfig

load_dotenv()

app = Flask(__name__)
client = GitHubAppClient(GitHubAppConfig.from_env())


@app.get("/")
def index():
    repos = client.list_org_repos()
    return render_template("index.html", repos=repos, org=client.config.org)


@app.post("/deploy")
def deploy():
    full_name = request.form.get("repo")
    if not full_name:
        return redirect(url_for("index"))

    ref = request.form.get("ref") or "main"
    client.dispatch_workflow(full_name, ref=ref)

    return render_template(
        "deploy.html",
        repo=full_name,
        ref=ref,
        runs_url=client.workflow_runs_url(),
        workflow_file=client.config.workflow_file,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
