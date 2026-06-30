# Fair Lending Intelligence Platform

An AI-powered platform for HMDA fair lending analysis, disparate impact detection,
conversational data exploration, and compliance reporting.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Browser (index.html)                            │
│   Upload │ Chat │ Search │ Fairness │ ML Engine │ Reports │ Monitor │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP / REST
┌─────────────────────────▼───────────────────────────────────────────┐
│                  FastAPI Backend (main.py)                           │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ /upload  │ │  /chat   │ │ /search  │ │/fairness │ │  /ml     │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       │            │            │             │             │       │
│  ┌────▼────────────▼────────────▼─────────────▼─────────────▼────┐ │
│  │                        Core Engines                            │ │
│  │  SchemaDiscovery │ DataProcessor │ NarrativeGen │ Chunker     │ │
│  │  Embedder        │ VectorStore   │ RAGEngine    │ FairnessEng │ │
│  │  MLEngine        │ Explainability│ ReportGen    │ Monitoring  │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
          │                    │                    │
   ┌──────▼──────┐    ┌────────▼────────┐   ┌──────▼──────┐
   │  ChromaDB   │    │  Google Gemini  │   │  Pickle     │
   │ (Vector DB) │    │   (LLM/Gen AI)  │   │  (ML Models)│
   └─────────────┘    └─────────────────┘   └─────────────┘
```

---

## Prerequisites

- Python 3.10 or higher
- pip (Python package installer)
- A Google AI Studio account for a Gemini API key (free tier available)

---

## Installation

### 1. Clone or download the project

```bash
cd fair-lending-platform
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the `backend/` directory:

```dotenv
# Required for AI chat features
GEMINI_API_KEY=your_api_key_here

# Optional overrides (defaults shown)
CHROMA_PERSIST_DIR=./chroma_db
UPLOAD_DIR=./uploads
MODELS_DIR=./models_store
```

### 5. Get a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **Create API Key**
4. Copy the key into your `.env` file

---

## Running the Application

### Start the Backend

```bash
cd fair-lending-platform

# From the project root (fair-lending-platform/)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API:** http://localhost:8000
- **Interactive Docs (Swagger):** http://localhost:8000/docs
- **Alternative Docs (ReDoc):** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

### Open the Frontend

Simply open `frontend/index.html` in your browser:

```bash
# macOS
open frontend/index.html

# Windows
start frontend/index.html

# Linux
xdg-open frontend/index.html
```

Or serve with a simple HTTP server:

```bash
cd frontend
python -m http.server 3000
# Then open http://localhost:3000
```

---

## Quick Start Workflow

1. **Upload a dataset** – drag and drop a CSV/XLSX lending file onto the Upload page
2. **Copy the File ID** from the uploads table
3. **Register for fairness analysis** – paste the File ID in the Fairness Dashboard
4. **Run Audit** – see disparate impact ratios and approval rates by demographic group
5. **Train ML model** – paste the File ID in ML Engine → Train Model
6. **Run batch predictions** – get risk scores for every applicant
7. **Chat** – ask the AI assistant questions about your data
8. **Download reports** – generate PDF compliance and fairness reports

---

## Feature Overview

| Feature | Description |
|---|---|
| 📊 **Schema Discovery** | Auto-maps arbitrary column names to canonical HMDA fields using fuzzy matching |
| 🧹 **Data Processing** | Deduplication, missing-value imputation, categorical standardisation |
| 📝 **Narrative Generation** | Converts structured records into natural-language applicant profiles |
| 🔍 **Semantic Search** | Vector similarity search across applicants, loans, and policy documents |
| 💬 **RAG Chat** | Conversational AI (Gemini) grounded in your actual data via ChromaDB |
| ⚖️ **Fairness Engine** | 4/5ths rule disparate impact analysis, approval rates by demographic group |
| 🤖 **ML Predictions** | RandomForest approval probability, IsolationForest anomaly detection, KMeans segmentation |
| 🔬 **Explainability** | SHAP-based feature attribution and natural-language prediction explanations |
| 📄 **Report Generation** | PDF/JSON fairness, compliance, risk, and executive reports via ReportLab |
| 📡 **Monitoring** | Real-time query tracking, fairness score trending, drift detection, alert management |

---

## API Reference

Base URL: `http://localhost:8000/api/v1`

### Upload
| Method | Path | Description |
|---|---|---|
| POST | `/upload/dataset` | Upload a tabular lending dataset |
| POST | `/upload/document` | Upload a policy/compliance document |
| GET | `/upload/status/{file_id}` | Check processing status |
| GET | `/upload/list` | List all uploaded files |

### Chat
| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Conversational RAG query |
| GET | `/chat/history/{session_id}` | Retrieve conversation history |
| DELETE | `/chat/session/{session_id}` | Clear a session |

### Search
| Method | Path | Description |
|---|---|---|
| POST | `/search/semantic` | General semantic search |
| POST | `/search/similar-applicants` | Find similar applicants |
| POST | `/search/similar-loans` | Find similar loans |
| POST | `/search/policy` | Search policy documents |

### Fairness
| Method | Path | Description |
|---|---|---|
| POST | `/fairness/register-dataset` | Register CSV data for analysis |
| POST | `/fairness/audit` | Run full fairness audit |
| GET | `/fairness/disparate-impact/{id}` | Disparate impact ratios |
| GET | `/fairness/approval-rates/{id}` | Approval rates by group |
| GET | `/fairness/score/{id}` | Overall fairness score |

### Machine Learning
| Method | Path | Description |
|---|---|---|
| POST | `/ml/train` | Train models on a dataset |
| POST | `/ml/predict` | Single applicant prediction |
| POST | `/ml/predict-batch` | Batch predictions |
| GET | `/ml/explain/{applicant_id}` | SHAP explanation |
| POST | `/ml/segments` | Applicant segmentation |
| POST | `/ml/anomalies` | Anomaly detection |

### Reports
| Method | Path | Description |
|---|---|---|
| POST | `/reports/fairness?format=pdf\|json` | Fairness audit report |
| POST | `/reports/compliance?format=pdf\|json` | Compliance report |
| POST | `/reports/risk?format=pdf\|json` | Risk assessment report |
| POST | `/reports/executive-summary?format=pdf\|json` | Executive summary |

---

## Project Structure

```
fair-lending-platform/
├── backend/
│   ├── main.py                  # FastAPI app, routers, middleware
│   ├── config.py                # Centralised configuration
│   ├── requirements.txt
│   ├── .env                     # (create this) environment variables
│   ├── api/
│   │   └── routes/
│   │       ├── upload.py        # Dataset & document ingestion
│   │       ├── chat.py          # RAG conversational endpoint
│   │       ├── search.py        # Semantic search endpoints
│   │       ├── fairness.py      # Fair lending analysis
│   │       ├── reports.py       # Report generation & download
│   │       └── ml.py            # ML training & inference
│   ├── core/
│   │   ├── schema_discovery.py  # Fuzzy column mapping
│   │   ├── data_processor.py    # Cleaning & quality scoring
│   │   ├── narrative_generator.py # Record → natural language
│   │   ├── synthetic_notes.py   # Template-based underwriting notes
│   │   ├── chunker.py           # Token-aware text splitting
│   │   ├── embedder.py          # SentenceTransformer singleton
│   │   ├── vector_store.py      # ChromaDB wrapper
│   │   ├── rag_engine.py        # Retrieval + Gemini generation
│   │   ├── fairness_engine.py   # Disparate impact & bias analysis
│   │   ├── ml_engine.py         # RandomForest, IsolationForest, KMeans
│   │   ├── explainability.py    # SHAP explanations
│   │   ├── report_generator.py  # PDF/JSON report creation
│   │   └── monitoring.py        # Metrics, drift, alerts
│   ├── models/
│   │   └── schemas.py           # Pydantic data models
│   └── utils/
│       └── helpers.py           # Shared utility functions
├── frontend/
│   ├── index.html               # Single-page application
│   ├── styles.css               # Custom CSS
│   └── app.js                   # Vanilla JS application logic
└── README.md
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | _(required for chat)_ | Google Gemini API key |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB storage path |
| `UPLOAD_DIR` | `./uploads` | Uploaded file storage path |
| `MODELS_DIR` | `./models_store` | Trained ML model storage |

---

## Technology Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI + Uvicorn |
| **LLM / Generation** | Google Gemini 1.5 Flash |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2) |
| **Vector Database** | ChromaDB (persistent) |
| **ML Models** | scikit-learn (RandomForest, IsolationForest, KMeans) |
| **Explainability** | SHAP |
| **Report Generation** | ReportLab |
| **Data Processing** | pandas, numpy, scipy |
| **Frontend** | Vanilla JS + Bootstrap 5 + Chart.js |

---

## License

Proprietary – for internal compliance and fair lending use.
