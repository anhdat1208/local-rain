from __future__ import annotations

import math
from typing import Any

from google.genai import types

TOOL_DECLARATIONS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="get_nearest_rain",
        description=(
            "Nearest rain cell to a location: distance, direction, ETA, motion, "
            "confidence, sky state, and advice from Local Rain radar."
        ),
        parameters={
            "type": "object",
            "properties": {
                "latitude": {"type": "number", "description": "Reference latitude"},
                "longitude": {"type": "number", "description": "Reference longitude"},
                "lang": {
                    "type": "string",
                    "enum": ["vi", "en"],
                    "description": "Response language for embedded advice fields",
                },
            },
            "required": ["latitude", "longitude"],
        },
    ),
    types.FunctionDeclaration(
        name="get_rain_vectors",
        description=(
            "Rain cells with movement vectors in an area. Each item has position, "
            "projected endpoint, speed, direction, and dBZ intensity."
        ),
        parameters={
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "radius_km": {
                    "type": "number",
                    "description": "Search radius in km (20-200)",
                },
                "limit": {
                    "type": "number",
                    "description": "Max vectors to return (1-16)",
                },
            },
            "required": ["latitude", "longitude"],
        },
    ),
    types.FunctionDeclaration(
        name="get_radar_state",
        description=(
            "Current radar availability: frame count, latest timestamp, "
            "radar age, and whether nowcast frames exist."
        ),
        parameters={"type": "object", "properties": {}},
    ),
    types.FunctionDeclaration(
        name="get_location_label",
        description="Reverse-geocode coordinates to a human-readable place name.",
        parameters={
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
            },
            "required": ["latitude", "longitude"],
        },
    ),
    types.FunctionDeclaration(
        name="get_rain_cell_near",
        description=(
            "Look up a rain cell near specific coordinates from current vectors. "
            "Use when user refers to a map point or selected cell."
        ),
        parameters={
            "type": "object",
            "properties": {
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "search_radius_km": {
                    "type": "number",
                    "description": "How far to search for a matching cell (default 15)",
                },
            },
            "required": ["latitude", "longitude"],
        },
    ),
]

GEMINI_TOOLS = types.Tool(function_declarations=TOOL_DECLARATIONS)
