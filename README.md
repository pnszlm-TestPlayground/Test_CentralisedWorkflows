# Centralised Workflows — Deploy POC

Proof of concept for a central repository that can **deploy other organisation
repos' code** using a **GitHub App** and **GitHub Actions**.

## How it works

1. The Flask app authenticates as a GitHub App using its **private key + JWT**
   (`iss`, `iat`, `exp`, RS256) and exchanges it for an **installation token**.
2. It lists every repo in the org the App can access and shows a **dropdown**.
3. When you pick a repo and click **Deploy**, the app calls the GitHub Actions
   REST API to send a **`workflow_dispatch`** event to the central workflow
   (`.github/workflows/deploy.yml`) with the selected repo as an input.
4. The workflow uses `actions/create-github-app-token` to mint a fresh
   installation token, **checks out the target repo**, and runs the deploy
   (currently simulated with `echo` steps).

```
dropdown -> POST /deploy
         -> POST /repos/{central}/actions/workflows/deploy.yml/dispatches
         -> workflow_dispatch(repo=org/target)
         -> checkout target repo (App token) -> deploy
```

## GitHub App permissions

| Scope        | Permission | Access          | Why                                          |
|--------------|------------|-----------------|----------------------------------------------|
| Repository   | Contents   | Read-only       | Clone/read code from org repos               |
| Repository   | Metadata   | Read-only       | Mandatory (always included)                  |
| Repository   | Actions    | Read and write  | Dispatch `workflow_dispatch` events via API  |
| Organization | Members    | Read-only (opt) | Only if you also list org members/teams      |

Install the App on your organisation with access to the repos you want to
deploy. The App's **App ID** and **private key** are needed in two places:

- `.env` (for the Flask app to list repos and dispatch workflows)
- central repo **secrets** `APP_ID` and `APP_PRIVATE_KEY` (for the workflow to
  generate its own token)

## Setup

1. Create a GitHub App (above permissions), install it on your org, download the
   private key and note the App ID.

2. Add the central repo secrets:

   - `APP_ID` → the App ID
   - `APP_PRIVATE_KEY` → the full PEM contents

3. Install dependencies and configure:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # set GITHUB_APP_ID, GITHUB_ORG, GITHUB_PRIVATE_KEY_PATH, GITHUB_CENTRAL_REPO
   ```

4. Run:

   ```bash
   python app.py          # http://localhost:5000
   ```

   Pick a repo, click Deploy, then view the run at
   `https://github.com/<central-repo>/actions/workflows/deploy.yml`.

## Auth flow (app)

```
private key (PEM)
    -> JWT (RS256, iss=App ID, exp=+10min)
    -> POST /app/installations/{id}/access_tokens
    -> installation token (scoped to App's permissions on the org)
    -> list org repos / dispatch workflow
```

The installation ID is auto-discovered from `GET /app/installations` unless
`GITHUB_INSTALLATION_ID` is set explicitly.
