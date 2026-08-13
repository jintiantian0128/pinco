# Pinco Technical Architecture & Design

## 1. System Overview
**Architecture Pattern**: Backend-for-Frontend (BFF) / Microservices Separation
- **Frontend**: Next.js (Node.js) - Handles UI, Auth, SSR, and Streaming.
- **Backend**: FastAPI (Python) - Handles Business Logic, AI Processing, DB operations.
- **Database**: PostgreSQL - Structured data (User profiles, Resumes, Chat logs).
- **Vector DB**: ChromaDB (Embedded) or pgvector - For RAG (Knowledge Base).

## 2. Design Choices (User-Centric)
- **Zero-Latency UI**: Optimistic UI updates for chat.
- **Streaming First**: Never make the user wait for a full AI response; stream tokens via SSE.
- **Mobile First**: Responsive design for users commuting or lying in bed (high anxiety moments).
- **Visual Feedback**: Clear status indicators for "Parsing Resume", "Thinking", "Generating Strategy".

## 3. API Contract (Draft)
- `POST /api/v1/chat/completions`: Main chat endpoint (Streaming).
- `POST /api/v1/resume/upload`: Multipart upload for PDF/Docx.
- `GET /api/v1/resume/{id}/analysis`: Get parsed data + AI score.

## 4. Tech Stack Details
- **Frontend**: Next.js 14, TailwindCSS, Framer Motion (Animations), Lucide React (Icons).
- **Backend**: Python 3.11+, FastAPI, Pydantic, SQLAlchemy, OpenAI SDK / LangChain.
- **Infra**: Docker Compose for local orchestration.
