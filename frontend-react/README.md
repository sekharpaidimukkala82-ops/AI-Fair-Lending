# FairLend AI — React Frontend

Enterprise Fair Lending Intelligence Platform — React + TypeScript + Vite

## Setup

```bash
cd frontend-react
npm install
npm run dev
```

Access at http://localhost:3001

## Default Login

- **Email:** admin@fairlend.ai
- **Password:** FairLend@Admin2024

## Environment

Backend must be running on http://localhost:8001

Start the backend first:
```bash
cd ..
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload
```

## Tech Stack

- **React 18** + **TypeScript** + **Vite**
- **TailwindCSS** — utility-first styling
- **TanStack Query** — server state management
- **Zustand** — client state (auth, dataset selection)
- **Recharts** — charts and data visualisation
- **Axios** — HTTP client with JWT interceptors
- **React Router v6** — client-side routing
- **React Hot Toast** — notifications
- **React Dropzone** — file upload UI

## Features

| Page | Description |
|------|-------------|
| Login / Register | JWT authentication with role-based access |
| Home | Platform overview, stats, quick start |
| Upload Data | Drag-and-drop file upload with processing status |
| AI Assistant | RAG-powered chat grounded in lending data |
| Semantic Search | Vector similarity search across records |
| Fairness Dashboard | Disparate impact analysis with charts |
| ML Engine | Model training, anomaly detection, clustering |
| Reports | Generate & download PDF/JSON compliance reports |
| Monitoring | System health, usage metrics, alert management |
| AI Settings | Configure AI provider, model, and API keys |
