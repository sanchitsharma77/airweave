#!/usr/bin/env node

/**
 * Airweave MCP Server - Stateless HTTP/Streamable Transport
 *
 * Production HTTP server for cloud-based AI platforms like OpenAI Agent Builder.
 * Uses the modern Streamable HTTP transport (MCP 2025-03-26).
 *
 * Fully stateless: a fresh McpServer + transport is created per request.
 * Authentication is per-request via headers. No sessions, no Redis.
 *
 * Endpoint: https://mcp.airweave.ai/mcp
 * Protocol: MCP 2025-03-26 (Streamable HTTP)
 * Authentication: X-API-Key, Bearer token, or query parameter
 */

import express from 'express';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpServer } from './server.js';
import { AirweaveConfig } from './api/types.js';
import { DEFAULT_BASE_URL } from './config/constants.js';

const app = express();
app.use(express.json({ limit: '10mb' }));

/**
 * Extract Bearer token per RFC 6750.
 * Returns undefined for non-Bearer schemes or malformed headers.
 */
function extractBearerToken(header: string | undefined): string | undefined {
    if (!header?.startsWith('Bearer ')) return undefined;
    return header.slice(7);
}

/**
 * Extract API key from request using multiple methods.
 */
function extractApiKey(req: express.Request): string | undefined {
    return (req.headers['x-api-key'] as string) ||
        extractBearerToken(req.headers['authorization'] as string) ||
        (req.query.apiKey as string) ||
        (req.query.api_key as string) ||
        undefined;
}

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({
        status: 'healthy',
        transport: 'streamable-http',
        protocol: 'MCP 2025-03-26',
        mode: 'stateless',
        timestamp: new Date().toISOString()
    });
});

// Root endpoint with server info
app.get('/', (req, res) => {
    res.json({
        name: "Airweave MCP Search Server",
        version: "0.5.7",
        transport: "Streamable HTTP",
        protocol: "MCP 2025-03-26",
        mode: "stateless",
        endpoints: {
            health: "/health",
            mcp: "/mcp"
        },
        authentication: {
            required: true,
            methods: [
                "X-API-Key: <your-api-key> (recommended)",
                "Authorization: Bearer <your-api-key>",
                "Query parameter: ?apiKey=your-key",
                "Query parameter: ?api_key=your-key"
            ],
            headers: {
                "X-API-Key": "Your Airweave API key (required)",
                "X-Collection-Readable-ID": "Collection readable ID to search (optional, falls back to env default)"
            },
            openai_agent_builder: {
                url: "https://mcp.airweave.ai/mcp",
                headers: {
                    "X-API-Key": "<your-airweave-api-key>",
                    "X-Collection-Readable-ID": "<your-collection-readable-id>"
                }
            }
        }
    });
});

// Main MCP endpoint - fully stateless, fresh server per request
app.post('/mcp', async (req, res) => {
    try {
        const apiKey = extractApiKey(req);

        if (!apiKey) {
            res.status(401).json({
                jsonrpc: '2.0',
                error: {
                    code: -32001,
                    message: 'Authentication required',
                    data: 'Please provide an API key via X-API-Key header, Authorization header, or apiKey query parameter'
                },
                id: req.body?.id || null
            });
            return;
        }

        const collection = (req.headers['x-collection-readable-id'] as string) ||
            process.env.AIRWEAVE_COLLECTION ||
            'default';
        const baseUrl = process.env.AIRWEAVE_BASE_URL || DEFAULT_BASE_URL;

        const config: AirweaveConfig = { apiKey, collection, baseUrl };
        const server = createMcpServer(config);

        const transport = new StreamableHTTPServerTransport({
            sessionIdGenerator: undefined
        });

        await server.connect(transport);
        await transport.handleRequest(req, res, req.body);

        // Clean up after the response is sent
        res.on('close', async () => {
            try {
                await transport.close();
                await server.close();
            } catch (err) {
                console.error(`[${new Date().toISOString()}] Error during cleanup:`, err);
            }
        });

    } catch (error) {
        console.error(`[${new Date().toISOString()}] Error handling MCP request:`, error);
        if (!res.headersSent) {
            res.status(500).json({
                jsonrpc: '2.0',
                error: {
                    code: -32603,
                    message: 'Internal server error',
                },
                id: req.body?.id || null
            });
        }
    }
});

// DELETE endpoint - no-op in stateless mode, return success for protocol compliance
app.delete('/mcp', (req, res) => {
    res.status(200).json({
        jsonrpc: '2.0',
        result: { message: 'Session terminated (stateless mode)' },
        id: null
    });
});

// Error handling middleware
app.use((error: Error, req: express.Request, res: express.Response, next: express.NextFunction) => {
    console.error(`[${new Date().toISOString()}] Unhandled error:`, error);
    if (!res.headersSent) {
        res.status(500).json({
            jsonrpc: '2.0',
            error: {
                code: -32603,
                message: 'Internal server error',
            },
            id: null
        });
    }
});

// Start server
async function startServer() {
    const PORT = process.env.PORT || 8080;
    const collection = process.env.AIRWEAVE_COLLECTION || 'default';
    const baseUrl = process.env.AIRWEAVE_BASE_URL || DEFAULT_BASE_URL;

    const server = app.listen(PORT, () => {
        console.log(`Airweave MCP Search Server (Streamable HTTP) started`);
        console.log(`Protocol: MCP 2025-03-26 | Mode: stateless`);
        console.log(`Endpoint: http://localhost:${PORT}/mcp`);
        console.log(`Health: http://localhost:${PORT}/health`);
        console.log(`Default collection: ${collection} | Base URL: ${baseUrl}`);
    });

    const shutdown = async (signal: string) => {
        console.log(`${signal} received. Shutting down...`);
        server.close(() => {
            console.log('HTTP server closed');
            process.exit(0);
        });
    };

    process.on('SIGTERM', () => shutdown('SIGTERM'));
    process.on('SIGINT', () => shutdown('SIGINT'));
}

startServer().catch((error) => {
    console.error('Failed to start server:', error);
    process.exit(1);
});
