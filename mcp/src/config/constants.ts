// Configuration constants for the MCP server

export const DEFAULT_BASE_URL = "https://api.airweave.ai";

export const ERROR_MESSAGES = {
    MISSING_API_KEY: "Error: AIRWEAVE_API_KEY environment variable is required",
    MISSING_COLLECTION: "Error: AIRWEAVE_COLLECTION environment variable is required",
} as const;
