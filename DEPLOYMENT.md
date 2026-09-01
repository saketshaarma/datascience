# Self-Hosting InfraForge

This portal (React + FastAPI + MongoDB) ships with two ways to run it in your own
environment: **Docker Compose** for a single host, and **Kubernetes manifests** for a cluster.

The React app talks to the backend at `${REACT_APP_BACKEND_URL}/api`. For self-hosting the
image is built with an **empty** `REACT_APP_BACKEND_URL`, so the browser calls `/api` on the
same origin and Nginx proxies that to the backend. This avoids CORS entirely.

---

## Option A — Docker Compose (single host)

Prerequisites: Docker Engine + the Compose plugin (`docker compose`).

```bash
# 1. Configure secrets
cp .env.example .env
#    Edit .env — at minimum set JWT_SECRET and ADMIN_PASSWORD.
#    Generate a secret with:  openssl rand -hex 32

# 2. Build and start (frontend + backend + mongo)
docker compose up -d --build

# 3. Open the portal
#    http://localhost:8080   (change with FRONTEND_PORT in .env)
```

The seed admin account (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) is created on first backend startup.

Useful commands:

```bash
docker compose logs -f backend      # tail backend logs
docker compose ps                   # service status
docker compose down                 # stop (keeps mongo volume)
docker compose down -v              # stop and delete the mongo volume
```

Services:
- `frontend` — Nginx serving the built React app, proxies `/api` → `backend:8001`
- `backend`  — FastAPI (uvicorn) on port 8001
- `mongo`    — MongoDB 7 with a named volume `mongo_data`

---

## Option B — Kubernetes

Prerequisites: a cluster, `kubectl`, an image registry, and (for `40-ingress.yaml`) an
ingress controller such as ingress-nginx.

### 1. Build & push images

```bash
# Backend
docker build -t <registry>/infraforge-backend:latest ./backend
docker push <registry>/infraforge-backend:latest

# Frontend (empty backend URL => same-origin /api)
docker build --build-arg REACT_APP_BACKEND_URL="" \
  -t <registry>/infraforge-frontend:latest ./frontend
docker push <registry>/infraforge-frontend:latest
```

Then set those image names in `k8s/20-backend.yaml` and `k8s/30-frontend.yaml`.
(If you use a local cluster like kind/minikube, load the images instead of pushing.)

### 2. Set secrets

Edit `k8s/01-secret.yaml` and replace `JWT_SECRET` / `ADMIN_PASSWORD` (and email if desired).

### 3. Apply

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-secret.yaml
kubectl apply -f k8s/02-configmap.yaml
kubectl apply -f k8s/10-mongo.yaml
kubectl apply -f k8s/20-backend.yaml
kubectl apply -f k8s/30-frontend.yaml
kubectl apply -f k8s/40-ingress.yaml     # optional; needs an ingress controller
```

Or all at once: `kubectl apply -f k8s/`

### 4. Access

- With ingress: point `infraforge.local` (or your domain) at the ingress controller and open it.
- Without ingress: port-forward the frontend:

  ```bash
  kubectl -n infraforge port-forward svc/infraforge-frontend 8080:80
  # open http://localhost:8080
  ```

---

## Configuration reference

| Variable         | Where              | Purpose                                        |
|------------------|--------------------|------------------------------------------------|
| `MONGO_URL`      | backend            | MongoDB connection string                      |
| `DB_NAME`        | backend            | Database name                                  |
| `JWT_SECRET`     | backend (secret)   | Signs JWT auth tokens — **must be strong**     |
| `ADMIN_EMAIL`    | backend (secret)   | Seed admin login                               |
| `ADMIN_PASSWORD` | backend (secret)   | Seed admin password                            |
| `CORS_ORIGINS`   | backend            | Allowed origins (unused for same-origin setup) |
| `FRONTEND_URL`   | backend            | Public URL, used for CORS on split deploys     |
| `BACKEND_HOST`   | frontend (Nginx)   | `host:port` the Nginx `/api` proxy targets     |
| `REACT_APP_BACKEND_URL` | frontend build arg | Leave empty for same-origin `/api`       |

### External / managed MongoDB
To use Atlas or another managed DB instead of the bundled one, set `MONGO_URL` to your
connection string (Compose: in `.env` + edit the `backend` service; K8s: in the ConfigMap)
and remove/skip the mongo Deployment.
