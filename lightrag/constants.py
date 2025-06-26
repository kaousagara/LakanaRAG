"""
Centralized configuration constants for LightRAG.

This module defines default values for configuration constants used across
different parts of the LightRAG system. Centralizing these values ensures
consistency and makes maintenance easier.
"""

# Default values for environment variables
DEFAULT_MAX_TOKEN_SUMMARY = 500
DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE = 6
DEFAULT_WOKERS = 2
DEFAULT_TIMEOUT = 150

# Logging configuration defaults
DEFAULT_LOG_MAX_BYTES = 10485760  # Default 10MB
DEFAULT_LOG_BACKUP_COUNT = 5  # Default 5 backups
DEFAULT_LOG_FILENAME = "lightrag.log"  # Default log filename

# External link base for entity names in responses
DEFAULT_ENTITY_LINK_BASE_URL = "https://example.com/entity/"

# Max content length for vector database fields to avoid oversized records
MAX_VECTOR_CONTENT_LENGTH = 65000

# Thresholds for graph relations
DEFAULT_MULTI_HOP_MIN_STRENGTH = 0.5
DEFAULT_LATENT_REL_MIN_STRENGTH = 0.5

# Enrichment feature toggles
DEFAULT_ENABLE_DESCRIPTION_ENRICHMENT = False
DEFAULT_ENABLE_GEO_ENRICHMENT = False
