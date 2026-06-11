# Google Cloud Deployment

## Local Container

```powershell
docker build -t energy-ops-agent:0.1.0 .
docker run --rm -p 8080:8080 energy-ops-agent:0.1.0
```

The container serves the FastAPI testing API. Check health and interactive docs:

```powershell
Invoke-WebRequest http://localhost:8080/v1/health -UseBasicParsing
```

Open `http://localhost:8080/docs` for browser-based testing.

## Cloud Run Shape

`cloudrun-service.yaml` defines:

- Cloud Run service
- port `8080`
- startup and liveness probes against `/v1/health`
- maximum one instance for bounded challenge-demo spend
- model and actor environment variables

## Public ADK UI

The public ADK web UI runs as a separate Cloud Run service so the local-style
agent console remains available without replacing the testing API:

```powershell
gcloud run deploy energy-ops-adk-ui `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --min-instances 0 `
  --max-instances 1 `
  --memory 1Gi `
  --cpu 1 `
  --command python `
  --args deploy/run_adk_web.py
```

`deploy/run_adk_web.py` starts:

```powershell
adk web startup_ops_agent --host 0.0.0.0 --port $env:PORT --no-reload
```

Before deploying, replace:

- `PROJECT_ID`
- Artifact Registry image path
- secret bindings

## Recommended Google Cloud Services

- Gemini Enterprise Agent Platform / Agent Engine for managed agent runtime
- Cloud Run for the API container
- Artifact Registry for container images
- Secret Manager for Gemini and connector credentials
- Cloud Logging for audit and operational logs
- Cloud Trace for request/tool latency
- Firestore or Cloud SQL for durable plans, simulation traces, and audit state

## Agent Engine Preparation

`agent-engine-deploy.py` records the expected Agent Engine deployment metadata.
It intentionally does not run in normal tests because actual deployment requires
Google Cloud credentials, an enabled project, staging bucket, and permissions.

Install cloud deployment tooling with:

```powershell
python -m pip install -e ".[cloud]"
```
