"""
FastAPI Core Application
Halyk Bank — Career Quest (HackAlem AI)
Team 202453
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from data_loader import (
    CustomProfileUploadRequest,
    CustomProfileUploadResponse,
    DataLoader,
    EmployeeProfile,
    get_data_loader,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize and warm up in-memory dataset
    loader = get_data_loader()
    yield
    # Shutdown hook if needed


app = FastAPI(
    title="Halyk Bank — Career Quest API",
    description="Explainable Multi-factor Career & Upskilling Recommendation Engine (Team 202453)",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", summary="Healthcheck & Dataset Status")
def healthcheck() -> Dict[str, Any]:
    loader = get_data_loader()
    stats = loader.get_stats()
    openai_key_configured = bool(os.getenv("OPENAI_API_KEY") and not os.getenv("OPENAI_API_KEY", "").startswith("your_"))
    return {
        "status": "healthy",
        "team_id": "202453",
        "project": "Halyk Bank Career Quest",
        "llm_ready": openai_key_configured,
        "dataset_stats": stats,
    }


@app.get("/api/profiles", response_model=List[EmployeeProfile], summary="List all employee profiles")
def list_profiles(include_custom: bool = True) -> List[EmployeeProfile]:
    loader = get_data_loader()
    return loader.get_all_employees(include_custom=include_custom)


@app.get("/api/profiles/{employee_id}", response_model=EmployeeProfile, summary="Get employee profile by ID")
def get_profile(employee_id: str) -> EmployeeProfile:
    loader = get_data_loader()
    profile = loader.get_employee(employee_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Employee profile '{employee_id}' not found")
    return profile


@app.post(
    "/api/profiles/upload",
    response_model=CustomProfileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload custom jury verification profiles (JSON body)",
)
def upload_custom_profiles(payload: CustomProfileUploadRequest) -> CustomProfileUploadResponse:
    """
    Core jury verification feature:
    Upload custom JSON profiles to test multi-factor recommendation against edge cases.
    Loaded dynamically into in-memory cache without server restarts.
    """
    loader = get_data_loader()
    loaded, errors = loader.load_custom_profiles(payload.profiles)
    
    return CustomProfileUploadResponse(
        status="success" if loaded else "failed",
        loaded_count=len(loaded),
        profile_ids=[p.id for p in loaded],
        validation_errors=errors,
    )


@app.post(
    "/api/profiles/upload-file",
    response_model=CustomProfileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload custom jury verification profiles (JSON file upload)",
)
async def upload_custom_profiles_file(file: UploadFile = File(...)) -> CustomProfileUploadResponse:
    """Accepts a JSON file upload containing custom candidate profiles for jury verification."""
    import json
    try:
        content = await file.read()
        parsed = json.loads(content.decode("utf-8"))
        if isinstance(parsed, dict):
            profiles = [parsed]
        elif isinstance(parsed, list):
            profiles = parsed
        else:
            raise ValueError("Expected JSON array or object")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {str(e)}")

    loader = get_data_loader()
    loaded, errors = loader.load_custom_profiles(profiles)
    return CustomProfileUploadResponse(
        status="success" if loaded else "failed",
        loaded_count=len(loaded),
        profile_ids=[p.id for p in loaded],
        validation_errors=errors,
    )


@app.get("/api/events", summary="List all upskilling events")
def list_events():
    loader = get_data_loader()
    return loader.get_events()


@app.get("/api/skills", summary="Get skills catalog and grade matrix")
def get_skills_matrix():
    loader = get_data_loader()
    return {
        "skills": list(loader._skills_catalog.values()),
        "grade_requirements": loader._grade_requirements,
    }
