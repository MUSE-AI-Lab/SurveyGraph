# -*- coding: utf-8 -*-
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Resource directory
RESOURCE_DIR = BASE_DIR / "resources"

# Output directory
OUTPUT_DIR = BASE_DIR / "outputs"

# Log directory
LOG_DIR = OUTPUT_DIR / "logs"

# Cache directory
CACHE_DIR = OUTPUT_DIR / "cache"

# Ensure directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# AI Image Generation Constants
AI_IMAGE_API_URL = os.getenv("AI_IMAGE_API_URL", "https://api.example.com/v1/images/generations")
AI_IMAGE_API_KEY = os.getenv("AI_IMAGE_API_KEY", "")
AI_IMAGE_MODEL = os.getenv("AI_IMAGE_MODEL", "gemini-3-pro-image-preview")
AI_IMAGE_MAX_PER_SURVEY = 5
AI_IMAGE_MAX_ITERATIONS = 2
AI_IMAGE_MIN_QUALITY_SCORE = 7.0
AI_IMAGE_PREFER_SURVEY_STYLE = True

# Multimodal API Constants
MULTIMODAL_API_URL = os.getenv("MULTIMODAL_API_URL", "")
MULTIMODAL_API_KEY = os.getenv("MULTIMODAL_API_KEY", "")
MULTIMODAL_MODEL = os.getenv("MULTIMODAL_MODEL", "gemini-1.5-pro")

# LLM API Constants
REMOTE_URL = os.getenv("REMOTE_URL", "")
TOKEN = os.getenv("TOKEN", "")
DEFAULT_CHATAGENT_MODEL = os.getenv("DEFAULT_CHATAGENT_MODEL", "gemini-1.5-pro")

# RAG Splitter Constants
DEFAULT_SPLITTER_TYPE = os.getenv("DEFAULT_SPLITTER_TYPE", "token")  # Options: "sentence", "semantic", "token", "hierarchical"
