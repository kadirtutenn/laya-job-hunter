# Local setup and sharing

This repository contains generic application code only. It must not contain a base CV, a candidate's contact details, job search history, browser cookies, or a user database.

## Install locally

Install Python 3.10+, then install [Ollaya](https://ollaya.dev/docs/quickstart) and run:

```bash
ollaya pull laya
ollaya serve
```

In another terminal:

```bash
git clone <REPOSITORY_URL>
cd laya-job-hunter
python3 -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -e .
python -m playwright install chromium
cp job_hunter/sample_profile.example.json job_hunter/sample_profile.json
```

Fill the ignored profile JSON from your own CV, then run:

```bash
python -m job_hunter --profile job_hunter/sample_profile.json serve
```

Open `http://127.0.0.1:8080`. The Ollaya service must remain running locally. Never put LinkedIn cookies, browser data, passwords, or API keys in the repository.

## Use with a coding agent

For full CV tailoring, add your base CV locally and give your coding agent the prompt in `job-hunter-friend-setup.md`. The prompt requires evidence-based claims, the L0–L7 decision layers, local-first defaults, and per-application human review. Keep CV files outside Git or under the ignored `candidate/` folder.

## Repository publishing checklist

Before making a repository public, review all tracked files and commit history. `.gitignore` only prevents future additions; it does not erase previously committed files. This starter has a fresh Git history and no candidate files. Choose a repository license before inviting third-party reuse.
