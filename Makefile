.PHONY: install data-server agent run ui docs docs-serve demo test clean

VENV := venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

install:
	$(PIP) install -r requirements.txt

data-server:
	$(UVICORN) data_servers.server:app --port 8001 --reload

agent:
	$(UVICORN) agent.main:app --port 8000 --reload

# Web UI — runs the data server in a background thread, no separate process needed.
ui:
	$(VENV)/bin/streamlit run streamlit_app.py

# Start both servers in the background for a quick demo.
run:
	$(UVICORN) data_servers.server:app --port 8001 & \
	$(UVICORN) agent.main:app --port 8000

# Build the documentation website (Markdown → static SPA in ./site).
docs:
	$(PY) docs/build.py

# Build, then serve the docs locally.
docs-serve: docs
	$(PY) -m http.server 8899 -d site

demo:
	curl -s -X POST http://localhost:8000/query \
		-H "Content-Type: application/json" \
		-d '{"query":"What is the sentiment around open source LLMs this week?","max_spend":0.05}' | $(PY) -m json.tool

test:
	$(VENV)/bin/pytest -q

clean:
	rm -f nexuspay.db
	find . -type d -name __pycache__ -exec rm -rf {} +
