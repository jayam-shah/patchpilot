   # PatchPilot

Automatically detects breaking API changes and opens a pull request to fix your code — before your users notice.

## The problem

When Stripe, Twilio, or OpenAI ships a breaking change, they post a changelog. Your codebase breaks silently. You find out when customers complain.

## The solution

PatchPilot watches API changelogs 24/7. When something changes, it scans your GitHub repo, generates a code fix using a local LLM, and opens a pull request automatically. You review and merge — nothing else.

## How it works

1. Register your GitHub repo and the API you use

2. PatchPilot polls the changelog every 24 hours

3. On a detected change, it scans your codebase for affected code

4. A local CodeLlama model generates the fix

5. A pull request is opened on your repo with the patched file

## Tech stack

- **FastAPI** — REST API and server

- **SQLite + SQLAlchemy** — local database

- **httpx + BeautifulSoup4** — changelog scraper

- **PyGithub** — repo scanning and PR creation

- **Ollama (CodeLlama 7B)** — local LLM for code patching, runs free on Apple Silicon

- **APScheduler** — 24-hour automatic pipeline

## Running locally

**Requirements:** Python 3.11, Ollama installed and running

```bash

git clone [https://github.com/jayam-shah/patchpilot.git](https://github.com/jayam-shah/patchpilot.git)

cd patchpilot

python3.11 -m venv venv

source venv/bin/activate

pip install -r requirements.txt

ollama pull codellama:7b

```

Create a `.env` file:  
  
GITHUB_TOKEN=your_github_personal_access_token  
OLLAMA_HOST=[http://localhost:11434](http://localhost:11434)  
  


Start the server:

```bash

uvicorn main:app --reload --port 8000

```

API docs available at `http://localhost:8000/docs`

## API endpoints

| Method | Endpoint | Description |

|--------|----------|-------------|

| GET | /health | Health check |

| POST | /repos | Register a GitHub repo to monitor |

| GET | /repos | List all monitored repos |

| GET | /patches | View patch history |

| DELETE | /repos/{id} | Stop monitoring a repo |

## Registering a repo

```bash

curl -X POST [http://localhost:8000/repos](http://localhost:8000/repos) \

  -H "Content-Type: application/json" \

  -d '{"github_url": "[https://github.com/your-username/your-repo](https://github.com/your-username/your-repo)", "api_name": "stripe"}'

```

## Status

MVP complete. Currently supports Stripe API monitoring for Python codebases.

Roadmap: multi-API support (Twilio, OpenAI), multi-language support, email notifications.

## Built by

Jayam Shah — MS Applied Data Intelligence, SJSU

[GitHub]([https://github.com/jayam-shah](https://github.com/jayam-shah)) · [LinkedIn]([https://www.linkedin.com/in/jayamshah2278/](https://www.linkedin.com/in/jayamshah2278/))
