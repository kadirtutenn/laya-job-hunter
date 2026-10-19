# Laya Job Hunter

A local-first, experimental job search and application tracking tool built with Python, Playwright, and Ollaya/Laya.

## What it does

- Search configured job boards and filter jobs by keyword and profile preferences.
- Score job/profile fit with deterministic checks and the local Laya decision service.
- Store jobs and workflow state in a local SQLite database.
- Open a local dashboard and prepare application forms for manual review.
- Generate a minimal resume using only fields the user entered in their local profile.

This is an MVP. Job board pages and access rules change. Follow each platform's terms and rate limits. The app does not promise that automation is permitted or that an account will avoid restrictions. Do not use it to bypass login, access controls, or platform limits. The application workflow fills forms but does not submit them.

## Requirements

- Python 3.10 or newer
- Ollaya installed locally with the `laya` model
- Chromium installed through Playwright

See [SETUP.md](SETUP.md) for detailed installation and privacy steps, and [DECISION_LAYERS.md](DECISION_LAYERS.md) for the L0–L7 architecture.

## Quick start

1. Install Ollaya using the [official quickstart](https://ollaya.dev/docs/quickstart), then run:

   ```bash
   ollaya pull laya
   ollaya serve
   ```

2. In another terminal, install this project:

   ```bash
   git clone <REPOSITORY_URL>
   cd laya-job-hunter
   python3 -m venv .venv
   source .venv/bin/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e .
   python -m playwright install chromium
   cp job_hunter/sample_profile.example.json job_hunter/sample_profile.json
   ```

3. Edit `job_hunter/sample_profile.json` with facts from your own CV. The file is ignored by Git. Keep your base CV, browser profile, and local job database on your device.
4. Start the local dashboard:

   ```bash
   python -m job_hunter --profile job_hunter/sample_profile.json serve
   ```

   Then open `http://127.0.0.1:8080`.

## Resume and AI limits

The starter profile ships empty. The minimal resume output includes only fields entered by the user. It does not parse a full CV or infer work history. Before using tailored CV generation, give your coding agent your own base CV and ask it to configure evidence-grounded CV editing. Never add claims just to match a job description.

Laya makes structured decisions; it does not write prose. No remote generative AI provider is configured by default. See [DECISION_LAYERS.md](DECISION_LAYERS.md).

## Privacy defaults

Candidate profile JSON, `candidate/`, browser data, `.env` files, SQLite data, generated resumes, and exported dashboard files are excluded by `.gitignore`. Review `git status` before every commit. Do not add credentials, cookies, or session files.

## License

No license has been added yet. Until the repository owner chooses a license, reuse rights are not granted by this repository.
