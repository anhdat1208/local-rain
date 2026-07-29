# Local Rain

AI-powered nowcasting web app: nearest rain, direction, distance, ETA, and go-outside advice.

## Stack

| Layer | Tech |
|-------|------|
| Web | Nuxt 4, Vue 3, TailwindCSS, Pinia, VueUse, MapLibre GL, PWA |
| API | Python 3.13, FastAPI, SQLAlchemy, PostgreSQL, Redis |
| Infra | Docker Compose |

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Web | http://localhost:3000 |
| API health | http://localhost:8000/api/health |
| API docs | http://localhost:8000/docs |

## Monorepo layout

```
apps/web     Nuxt frontend
apps/api     FastAPI backend
packages/shared   Shared TypeScript contracts
```

## Day 1 status

Bootstrap only: folder structure, Docker Compose, Nuxt + FastAPI skeletons, Postgres, Redis.
