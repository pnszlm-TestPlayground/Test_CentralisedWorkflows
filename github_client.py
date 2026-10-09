import os
import time
import urllib.parse
from dataclasses import dataclass

import jwt
import requests


@dataclass
class GitHubAppConfig:
    app_id: str
    org: str
    private_key: str
    installation_id: int | None
    api_url: str
    central_repo: str
    workflow_file: str

    @classmethod
    def from_env(cls) -> "GitHubAppConfig":
        app_id = os.environ.get("GITHUB_APP_ID", "").strip()
        org = os.environ.get("GITHUB_ORG", "").strip()
        if not app_id or not org:
            raise RuntimeError("GITHUB_APP_ID and GITHUB_ORG must be set")

        private_key = os.environ.get("GITHUB_PRIVATE_KEY", "")
        if not private_key:
            key_path = os.environ.get("GITHUB_PRIVATE_KEY_PATH", "private-key.pem")
            with open(key_path, "r") as fh:
                private_key = fh.read()

        installation_id = os.environ.get("GITHUB_INSTALLATION_ID", "").strip()
        central_repo = os.environ.get("GITHUB_CENTRAL_REPO", "").strip()
        if not central_repo:
            raise RuntimeError("GITHUB_CENTRAL_REPO must be set (org/central-repo)")
        return cls(
            app_id=app_id,
            org=org,
            private_key=private_key,
            installation_id=int(installation_id) if installation_id else None,
            api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
            central_repo=central_repo,
            workflow_file=os.environ.get("GITHUB_WORKFLOW_FILE", "deploy.yml").strip(),
        )


class GitHubAppClient:
    def __init__(self, config: GitHubAppConfig):
        self.config = config
        self._jwt: str | None = None
        self._jwt_expiry = 0

    def _app_jwt(self) -> str:
        if self._jwt and time.time() < self._jwt_expiry - 30:
            return self._jwt
        now = int(time.time())
        payload = {
            "iat": now,
            "exp": now + (10 * 60),
            "iss": self.config.app_id,
        }
        self._jwt = jwt.encode(payload, self.config.private_key, algorithm="RS256")
        self._jwt_expiry = now + (10 * 60)
        return self._jwt

    def _request(self, method: str, path: str, *, token: str | None = None, **kwargs) -> dict:
        url = f"{self.config.api_url}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def resolve_installation_id(self) -> int:
        if self.config.installation_id:
            return self.config.installation_id
        data = self._request("GET", "/app/installations", token=self._app_jwt())
        for installation in data:
            account = installation.get("account", {})
            if account.get("login", "").lower() == self.config.org.lower():
                return installation["id"]
        raise RuntimeError(f"No installation found for org {self.config.org}")

    def installation_token(self) -> str:
        installation_id = self.resolve_installation_id()
        data = self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            token=self._app_jwt(),
        )
        return data["token"]

    def list_org_repos(self) -> list[dict]:
        token = self.installation_token()
        repos = []
        page = 1
        while True:
            data = self._request(
                "GET",
                f"/orgs/{urllib.parse.quote(self.config.org)}/repos",
                token=token,
                params={"per_page": 100, "page": page, "sort": "full_name"},
            )
            repos.extend(data)
            if len(data) < 100:
                break
            page += 1
        return repos

    def repo_file_tree(self, full_name: str) -> list[dict]:
        token = self.installation_token()
        owner, repo = full_name.split("/", 1)
        repo_info = self._request("GET", f"/repos/{owner}/{repo}", token=token)
        default_branch = repo_info.get("default_branch", "main")
        tree = self._request(
            "GET",
            f"/repos/{owner}/{repo}/git/trees/{default_branch}",
            token=token,
            params={"recursive": 1},
        )
        return tree.get("tree", [])

    def repo_default_branch(self, full_name: str) -> str:
        token = self.installation_token()
        owner, repo = full_name.split("/", 1)
        return self._request("GET", f"/repos/{owner}/{repo}", token=token).get(
            "default_branch", "main"
        )

    def dispatch_workflow(self, target_repo: str, ref: str = "main") -> None:
        token = self.installation_token()
        owner, repo = self.config.central_repo.split("/", 1)
        workflow_file = urllib.parse.quote(self.config.workflow_file)
        self._request(
            "POST",
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches",
            token=token,
            json={"ref": ref, "inputs": {"repo": target_repo, "ref": ref}},
        )

    def workflow_runs_url(self) -> str:
        return (
            f"https://github.com/{self.config.central_repo}/actions/workflows/"
            f"{urllib.parse.quote(self.config.workflow_file)}"
        )
