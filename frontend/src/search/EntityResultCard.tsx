import React, { useState, useMemo } from 'react';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { materialOceanic, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { ChevronDown, ChevronRight, ExternalLink, Copy, Check, Link as LinkIcon, Clock } from 'lucide-react';
import { getAppIconUrl } from '@/lib/utils/icons';
import { useTheme } from '@/lib/theme-provider';

interface EntityResultCardProps {
    result: any;
    index: number;
    isDark: boolean;
    onEntityIdClick?: (entityId: string) => void;
}

/**
 * Parse embeddable text to extract structured information
 * Looks for patterns like "* type: Page", "* Context: ...", etc.
 */
const parseEmbeddableText = (text: string) => {
    const lines = text.split('\n');
    const structured: Record<string, string> = {};
    const remainingContent: string[] = [];
    let inContentSection = false;

    for (const line of lines) {
        const trimmed = line.trim();

        // Match patterns like "* key: value" or "* key value"
        const match = trimmed.match(/^\*\s+([^:]+):\s*(.+)$/);
        if (match && !inContentSection) {
            const [, key, value] = match;
            const normalizedKey = key.toLowerCase().trim();

            // Store structured fields
            if (['type', 'source', 'context', 'title', 'name'].includes(normalizedKey)) {
                structured[normalizedKey] = value.trim();
            } else {
                // Once we hit non-standard fields, consider it content
                inContentSection = true;
                remainingContent.push(line);
            }
        } else if (trimmed.startsWith('* ') && !inContentSection) {
            // Handle "* name value" format (without colon)
            const parts = trimmed.substring(2).split(/\s+/);
            if (parts.length >= 2) {
                const key = parts[0].toLowerCase();
                const value = parts.slice(1).join(' ');
                if (['type', 'source', 'context', 'title', 'name'].includes(key)) {
                    structured[key] = value;
                } else {
                    inContentSection = true;
                    remainingContent.push(line);
                }
            }
        } else {
            // Regular content
            inContentSection = true;
            if (trimmed) {
                remainingContent.push(line);
            }
        }
    }

    return {
        structured,
        content: remainingContent.join('\n').trim()
    };
};

/**
 * EntityResultCard - A human-readable card view for entity search results
 */
export const EntityResultCard: React.FC<EntityResultCardProps> = ({
    result,
    index,
    isDark,
    onEntityIdClick
}) => {
    const [isMetadataExpanded, setIsMetadataExpanded] = useState(false);
    const [isContentExpanded, setIsContentExpanded] = useState(false);
    const [isRawExpanded, setIsRawExpanded] = useState(false);
    const [copiedField, setCopiedField] = useState<string | null>(null);
    const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set());
    const { resolvedTheme } = useTheme();

    // Extract payload from result
    const payload = result.payload || result;
    const score = result.score;

    // Determine if score looks like cosine similarity (0-1 range) or something else
    const isNormalizedScore = score !== undefined && score >= 0 && score <= 1;

    // Format score for display
    const getScoreDisplay = () => {
        if (score === undefined) return null;

        // For scores in 0-1 range (cosine similarity), show as percentage
        if (isNormalizedScore) {
            return {
                value: `${(score * 100).toFixed(1)}%`,
                color: score >= 0.7 ? 'green' : score >= 0.5 ? 'yellow' : 'gray'
            };
        }

        // For other scores (e.g., BM25), show raw value
        return {
            value: score.toFixed(3),
            color: score >= 10 ? 'green' : score >= 5 ? 'yellow' : 'gray'
        };
    };

    const scoreDisplay = getScoreDisplay();

    // Extract key fields
    const entityId = payload.entity_id || payload.id || payload._id;
    const sourceName = payload.airweave_system_metadata?.source_name || payload.source_name || 'Unknown Source';
    const sourceIconUrl = getAppIconUrl(sourceName, resolvedTheme);
    const embeddableText = payload.embeddable_text || '';
    const breadcrumbs = payload.breadcrumbs || [];
    const url = payload.url;
    const mdContent = payload.md_content;

    // Parse embeddable text for structured information
    const { structured, content } = useMemo(() => parseEmbeddableText(embeddableText), [embeddableText]);

    // Extract title from structured data or fallback
    const title = structured.title || structured.name || payload.md_title || payload.title || payload.name || 'Untitled';
    const entityType = structured.type || 'Document';
    const context = structured.context || (breadcrumbs.length > 0 ? breadcrumbs.map((b: any) =>
        typeof b === 'string' ? b : b.name || b.title || ''
    ).filter(Boolean).join(' > ') : '');

    // Get Airweave logo based on theme
    const airweaveLogo = isDark
        ? '/airweave-logo-svg-white-darkbg.svg'
        : '/airweave-logo-svg-lightbg-blacklogo.svg';

    // Format source name (capitalize first letter of each word)
    const formattedSourceName = sourceName
        .split('_')
        .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
        .join(' ');

    // Extract metadata (exclude system fields and already displayed fields)
    const metadata = useMemo(() => {
        const filtered: Record<string, any> = {};
        const excludeKeys = [
            'entity_id', 'id', '_id',
            'embeddable_text', 'md_content', 'md_title',
            'title', 'name', 'breadcrumbs', 'url',
            'airweave_system_metadata', 'source_name',
            'download_url', 'local_path', 'file_uuid', 'checksum',
            'vector', 'vectors'
        ];

        Object.entries(payload).forEach(([key, value]) => {
            if (!excludeKeys.includes(key) && value !== null && value !== undefined && value !== '') {
                // Format key names nicely
                const formattedKey = key
                    .split('_')
                    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                    .join(' ');
                filtered[formattedKey] = value;
            }
        });

        return filtered;
    }, [payload]);

    const hasMetadata = Object.keys(metadata).length > 0;

    // Prioritize important fields and limit display
    const IMPORTANT_FIELDS = ['Owner', 'Assignee', 'Status', 'Priority', 'Due Date', 'Created At', 'Updated At', 'Author', 'Completion', 'Tags', 'Labels'];
    const MAX_FIELDS_DEFAULT = 4; // Show max 4 fields by default

    const { importantMetadata, remainingMetadata } = useMemo(() => {
        const important: Record<string, any> = {};
        const remaining: Record<string, any> = {};

        // First, collect important fields
        Object.entries(metadata).forEach(([key, value]) => {
            if (IMPORTANT_FIELDS.some(field => key.toLowerCase().includes(field.toLowerCase()))) {
                important[key] = value;
            } else {
                remaining[key] = value;
            }
        });

        // If we have fewer than MAX_FIELDS_DEFAULT important fields, add some remaining ones
        const importantCount = Object.keys(important).length;
        if (importantCount < MAX_FIELDS_DEFAULT) {
            const remainingEntries = Object.entries(remaining);
            const toAdd = remainingEntries.slice(0, MAX_FIELDS_DEFAULT - importantCount);
            toAdd.forEach(([key, value]) => {
                important[key] = value;
                delete remaining[key];
            });
        }

        return { importantMetadata: important, remainingMetadata: remaining };
    }, [metadata]);

    const hasRemainingMetadata = Object.keys(remainingMetadata).length > 0;

    // Copy to clipboard handler
    const handleCopy = async (text: string, fieldName: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopiedField(fieldName);
            setTimeout(() => setCopiedField(null), 2000);
        } catch (error) {
            console.error('Failed to copy:', error);
        }
    };

    // Toggle field expansion
    const toggleFieldExpansion = (fieldKey: string) => {
        setExpandedFields(prev => {
            const newSet = new Set(prev);
            if (newSet.has(fieldKey)) {
                newSet.delete(fieldKey);
            } else {
                newSet.add(fieldKey);
            }
            return newSet;
        });
    };

    // Format date/timestamp values
    const formatDate = (dateString: string): string => {
        try {
            const date = new Date(dateString);
            if (isNaN(date.getTime())) {
                return dateString; // Not a valid date
            }

            // Format as: "Jan 5, 2025 at 12:17 PM"
            const formatted = date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
            }) + ' at ' + date.toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true
            });

            // Add relative time for recent dates
            const now = new Date();
            const diffMs = now.getTime() - date.getTime();
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

            if (diffDays === 0) {
                return `Today at ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
            } else if (diffDays === 1) {
                return `Yesterday at ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
            } else if (diffDays < 7) {
                return `${diffDays} days ago`;
            }

            return formatted;
        } catch (error) {
            return dateString;
        }
    };

    // Check if a value is a date/timestamp
    const isDateField = (key: string, value: any): boolean => {
        if (typeof value !== 'string') return false;

        // Check if field name suggests it's a date
        const dateFieldPatterns = ['date', 'time', 'created', 'updated', 'modified', 'deleted', 'scheduled'];
        const lowerKey = key.toLowerCase();
        if (!dateFieldPatterns.some(pattern => lowerKey.includes(pattern))) {
            return false;
        }

        // Check if value matches ISO date format
        const isoDateRegex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
        return isoDateRegex.test(value);
    };

    // Format and truncate field value
    const formatFieldValue = (value: any, key: string, maxLength: number = 150) => {
        let stringValue: string;

        // Check if it's a date field and format it nicely
        if (isDateField(key, value)) {
            stringValue = formatDate(value);
        } else if (typeof value === 'object' && value !== null) {
            stringValue = JSON.stringify(value, null, 2);
        } else {
            stringValue = String(value);
        }

        const isExpanded = expandedFields.has(key);
        const needsTruncation = stringValue.length > maxLength;

        if (!needsTruncation) {
            return { displayValue: stringValue, needsTruncation: false, isDate: isDateField(key, value) };
        }

        if (isExpanded) {
            return { displayValue: stringValue, needsTruncation: true, isDate: isDateField(key, value) };
        }

        return {
            displayValue: stringValue.substring(0, maxLength) + '...',
            needsTruncation: true,
            isDate: isDateField(key, value)
        };
    };

    // Memoized syntax style
    const syntaxStyle = useMemo(() => isDark ? materialOceanic : oneLight, [isDark]);

    return (
        <div
            className={cn(
                "group relative rounded-xl transition-all duration-300 overflow-hidden",
                isDark
                    ? "bg-gradient-to-br from-gray-900/90 to-gray-900/50 border border-gray-800/50 hover:border-gray-700/70 hover:shadow-2xl hover:shadow-blue-900/10"
                    : "bg-white border border-gray-200/60 hover:border-gray-300/80 hover:shadow-lg hover:shadow-gray-200/50",
                "backdrop-blur-sm"
            )}
        >
            {/* Header Section */}
            <div className={cn(
                "px-5 py-4",
                isDark ? "border-b border-gray-800/50" : "border-b border-gray-100"
            )}>
                <div className="flex items-start justify-between gap-4">
                    {/* Title with Icon */}
                    <div className="flex-1 min-w-0">
                        <div className="flex items-start gap-3">
                            {/* Clean Airweave Logo - no overlay */}
                            <div className={cn(
                                "flex-shrink-0 w-9 h-9 rounded-lg flex items-center justify-center overflow-hidden",
                                isDark ? "bg-gray-800/50" : "bg-gray-50"
                            )}>
                                <img
                                    src={airweaveLogo}
                                    alt="Airweave"
                                    className="w-full h-full object-contain p-1.5 opacity-40"
                                />
                            </div>
                            <div className="flex-1 min-w-0 pt-0.5">
                                <h3 className={cn(
                                    "text-[15px] font-semibold mb-2 break-words leading-snug tracking-tight",
                                    isDark ? "text-gray-50" : "text-gray-900"
                                )}>
                                    {title}
                                </h3>

                                {/* Context and Type */}
                                <div className="flex flex-wrap items-center gap-2 mb-2">
                                    {/* Source Icon Badge */}
                                    <span className={cn(
                                        "inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded-md text-[11px] font-medium",
                                        isDark
                                            ? "bg-gray-800/40 border border-gray-700/40"
                                            : "bg-gray-50/60 border border-gray-200/50"
                                    )}>
                                        <div className="w-4 h-4 rounded-sm overflow-hidden flex items-center justify-center flex-shrink-0">
                                            <img
                                                src={sourceIconUrl}
                                                alt={formattedSourceName}
                                                className="w-full h-full object-contain"
                                                onError={(e) => {
                                                    // Fallback to first letter if icon fails
                                                    const target = e.target as HTMLImageElement;
                                                    target.style.display = 'none';
                                                    const parent = target.parentElement;
                                                    if (parent) {
                                                        parent.classList.add(isDark ? 'bg-gray-700' : 'bg-gray-200');
                                                        parent.innerHTML = `<span class="text-[9px] font-semibold ${isDark ? 'text-gray-300' : 'text-gray-600'}">${formattedSourceName.charAt(0)}</span>`;
                                                    }
                                                }}
                                            />
                                        </div>
                                        <span className={cn(
                                            "text-[11px]",
                                            isDark ? "text-gray-400" : "text-gray-600"
                                        )}>
                                            {formattedSourceName}
                                        </span>
                                    </span>

                                    {context && (
                                        <span className={cn(
                                            "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium",
                                            isDark
                                                ? "bg-gray-800/60 text-gray-300 border border-gray-700/50"
                                                : "bg-gray-50 text-gray-600 border border-gray-200/60"
                                        )}>
                                            {context}
                                        </span>
                                    )}
                                    <span className={cn(
                                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium",
                                        isDark
                                            ? "bg-blue-950/40 text-blue-300 border border-blue-900/50"
                                            : "bg-blue-50/80 text-blue-700 border border-blue-200/60"
                                    )}>
                                        {entityType}
                                    </span>
                                </div>

                                {/* URL Link */}
                                {url && (
                                    <a
                                        href={url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className={cn(
                                            "inline-flex items-center gap-1.5 text-[12px] font-medium transition-all duration-200 hover:gap-2",
                                            isDark
                                                ? "text-blue-400 hover:text-blue-300"
                                                : "text-blue-600 hover:text-blue-700"
                                        )}
                                    >
                                        <ExternalLink className="h-3 w-3" />
                                        Open in {formattedSourceName}
                                    </a>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Top-right badges: Result number + Score */}
                    <div className="flex flex-col items-end gap-2">
                        {/* Result Number Badge */}
                        <div className={cn(
                            "flex-shrink-0 px-2 py-0.5 rounded-md text-[10px] font-bold font-mono",
                            isDark
                                ? "bg-gray-800/60 text-gray-400 border border-gray-700/50"
                                : "bg-gray-100 text-gray-500 border border-gray-200/60"
                        )}>
                            #{index + 1}
                        </div>

                        {/* Score Badge */}
                        {scoreDisplay && (
                            <div
                                className={cn(
                                    "flex-shrink-0 px-2.5 py-1 rounded-lg text-[11px] font-semibold font-mono whitespace-nowrap transition-colors cursor-help",
                                    // Green for high scores
                                    scoreDisplay.color === 'green' && (
                                        isDark
                                            ? "bg-green-950/40 text-green-400 border border-green-900/50"
                                            : "bg-green-50 text-green-700 border border-green-200/60"
                                    ),
                                    // Yellow for medium scores
                                    scoreDisplay.color === 'yellow' && (
                                        isDark
                                            ? "bg-yellow-950/40 text-yellow-400 border border-yellow-900/50"
                                            : "bg-yellow-50 text-yellow-700 border border-yellow-200/60"
                                    ),
                                    // Gray for low scores
                                    scoreDisplay.color === 'gray' && (
                                        isDark
                                            ? "bg-gray-800/60 text-gray-400 border border-gray-700/50"
                                            : "bg-gray-100 text-gray-600 border border-gray-300/60"
                                    )
                                )}
                                title={
                                    isNormalizedScore
                                        ? `Similarity score: ${score.toFixed(4)} (${score >= 0.7 ? 'Excellent' : score >= 0.5 ? 'Good' : 'Fair'} match)`
                                        : `Relevance score: ${score.toFixed(3)}`
                                }
                            >
                                {scoreDisplay.value}
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Important Metadata Fields - Always visible (max 4) */}
            {Object.keys(importantMetadata).length > 0 && (
                <div className={cn(
                    "px-5 py-4",
                    isDark ? "bg-gray-900/20 border-y border-gray-800/50" : "bg-gray-50/50 border-y border-gray-100"
                )}>
                    <div className="grid grid-cols-2 gap-x-8 gap-y-4">
                        {Object.entries(importantMetadata).map(([key, value]) => {
                            const { displayValue, needsTruncation, isDate } = formatFieldValue(value, key);
                            const isExpanded = expandedFields.has(key);

                            return (
                                <div key={key} className="flex flex-col gap-1.5">
                                    <div className="flex items-start gap-3">
                                        <span className={cn(
                                            "text-[11px] font-semibold uppercase tracking-wider min-w-[90px] pt-0.5",
                                            isDark ? "text-gray-500" : "text-gray-500"
                                        )}>
                                            {key}
                                        </span>
                                        <span className={cn(
                                            "text-[13px] break-words flex-1 leading-relaxed",
                                            isDate && "inline-flex items-center gap-1.5",
                                            isDark ? "text-gray-200" : "text-gray-700"
                                        )}>
                                            {isDate && <Clock className="h-3.5 w-3.5 opacity-60 flex-shrink-0" />}
                                            {displayValue}
                                        </span>
                                    </div>
                                    {needsTruncation && (
                                        <button
                                            onClick={() => toggleFieldExpansion(key)}
                                            className={cn(
                                                "text-[11px] font-medium self-start ml-[90px] transition-all duration-200 hover:translate-x-0.5",
                                                isDark
                                                    ? "text-blue-400 hover:text-blue-300"
                                                    : "text-blue-600 hover:text-blue-700"
                                            )}
                                        >
                                            {isExpanded ? '← Show Less' : 'Show More →'}
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* Show More/Less Button for Additional Metadata */}
                    {hasRemainingMetadata && (
                        <>
                            <button
                                onClick={() => setIsMetadataExpanded(!isMetadataExpanded)}
                                className={cn(
                                    "mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200",
                                    isDark
                                        ? "text-blue-400 hover:text-blue-300 bg-blue-950/30 hover:bg-blue-950/50 border border-blue-900/50"
                                        : "text-blue-600 hover:text-blue-700 bg-blue-50/50 hover:bg-blue-50 border border-blue-200/60"
                                )}
                            >
                                {isMetadataExpanded ? (
                                    <>
                                        <ChevronDown className="h-3.5 w-3.5" />
                                        Show Less
                                    </>
                                ) : (
                                    <>
                                        <ChevronRight className="h-3.5 w-3.5" />
                                        {Object.keys(remainingMetadata).length} More Field{Object.keys(remainingMetadata).length !== 1 ? 's' : ''}
                                    </>
                                )}
                            </button>

                            {/* Additional Metadata - Collapsible */}
                            {isMetadataExpanded && (
                                <div className={cn(
                                    "grid grid-cols-2 gap-x-8 gap-y-4 mt-4 pt-4",
                                    isDark ? "border-t border-gray-800/50" : "border-t border-gray-200/50"
                                )}>
                                    {Object.entries(remainingMetadata).map(([key, value]) => {
                                        const { displayValue, needsTruncation, isDate } = formatFieldValue(value, key);
                                        const isExpanded = expandedFields.has(key);

                                        return (
                                            <div key={key} className="flex flex-col gap-1.5">
                                                <div className="flex items-start gap-3">
                                                    <span className={cn(
                                                        "text-[11px] font-semibold uppercase tracking-wider min-w-[90px] pt-0.5",
                                                        isDark ? "text-gray-500" : "text-gray-500"
                                                    )}>
                                                        {key}
                                                    </span>
                                                    <span className={cn(
                                                        "text-[13px] break-words flex-1 leading-relaxed",
                                                        isDate && "inline-flex items-center gap-1.5",
                                                        isDark ? "text-gray-200" : "text-gray-700"
                                                    )}>
                                                        {isDate && <Clock className="h-3.5 w-3.5 opacity-60 flex-shrink-0" />}
                                                        {displayValue}
                                                    </span>
                                                </div>
                                                {needsTruncation && (
                                                    <button
                                                        onClick={() => toggleFieldExpansion(key)}
                                                        className={cn(
                                                            "text-[11px] font-medium self-start ml-[90px] transition-all duration-200 hover:translate-x-0.5",
                                                            isDark
                                                                ? "text-blue-400 hover:text-blue-300"
                                                                : "text-blue-600 hover:text-blue-700"
                                                        )}
                                                    >
                                                        {isExpanded ? '← Show Less' : 'Show More →'}
                                                    </button>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}

            {/* Main Content - Parsed content from embeddable text */}
            {content && (
                <div className={cn(
                    "px-5 py-4",
                    isDark ? "text-gray-200" : "text-gray-800"
                )}>
                    <div className="relative">
                        <button
                            onClick={() => handleCopy(content, 'content')}
                            className={cn(
                                "absolute top-0 right-0 p-1.5 rounded-lg transition-all duration-200 z-10",
                                isDark
                                    ? "hover:bg-gray-800/80 text-gray-400 hover:text-gray-300"
                                    : "hover:bg-gray-100 text-gray-600 hover:text-gray-700"
                            )}
                            title="Copy content"
                        >
                            {copiedField === 'content' ? (
                                <Check className="h-3.5 w-3.5" />
                            ) : (
                                <Copy className="h-3.5 w-3.5" />
                            )}
                        </button>

                        {/* Container for content with truncation */}
                        <div className="relative">
                            <div className={cn(
                                !isContentExpanded && content.length > 500 && "max-h-[200px] overflow-hidden"
                            )}>
                                <ReactMarkdown
                                    remarkPlugins={[remarkGfm]}
                                    components={{
                                        h1: ({ node, ...props }) => <h1 className="text-base font-bold mt-4 mb-2 first:mt-0" {...props} />,
                                        h2: ({ node, ...props }) => <h2 className="text-sm font-bold mt-3 mb-2 first:mt-0" {...props} />,
                                        h3: ({ node, ...props }) => <h3 className="text-sm font-semibold mt-3 mb-1.5 first:mt-0" {...props} />,
                                        p: ({ node, ...props }) => <p className="text-[13px] leading-relaxed mb-2" {...props} />,
                                        ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-2 space-y-1 text-[13px]" {...props} />,
                                        ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-2 space-y-1 text-[13px]" {...props} />,
                                        li: ({ node, ...props }) => <li className="text-[13px] leading-relaxed" {...props} />,
                                        blockquote: ({ node, ...props }) => (
                                            <blockquote className={cn(
                                                "border-l-4 pl-3 my-2 italic text-[13px]",
                                                isDark ? "border-gray-600 text-gray-400" : "border-gray-300 text-gray-600"
                                            )} {...props} />
                                        ),
                                        code(props) {
                                            const { children, className, node, ...rest } = props;
                                            const match = /language-(\w+)/.exec(className || '');
                                            return match ? (
                                                <SyntaxHighlighter
                                                    language={match[1]}
                                                    style={syntaxStyle}
                                                    customStyle={{
                                                        margin: '0.5rem 0',
                                                        borderRadius: '0.375rem',
                                                        fontSize: '0.75rem',
                                                        padding: '0.75rem',
                                                        background: isDark ? 'rgba(17, 24, 39, 0.8)' : 'rgba(249, 250, 251, 0.95)'
                                                    }}
                                                >
                                                    {String(children).replace(/\n$/, '')}
                                                </SyntaxHighlighter>
                                            ) : (
                                                <code className={cn(
                                                    "px-1.5 py-0.5 rounded text-[11px] font-mono",
                                                    isDark
                                                        ? "bg-gray-800 text-gray-300"
                                                        : "bg-gray-100 text-gray-800"
                                                )} {...rest}>
                                                    {children}
                                                </code>
                                            );
                                        },
                                        strong: ({ node, ...props }) => <strong className="font-semibold" {...props} />,
                                        em: ({ node, ...props }) => <em className="italic" {...props} />,
                                    }}
                                >
                                    {content}
                                </ReactMarkdown>
                            </div>

                            {/* Fade overlay when content is truncated */}
                            {!isContentExpanded && content.length > 500 && (
                                <div className={cn(
                                    "absolute bottom-0 left-0 right-0 h-16 pointer-events-none",
                                    isDark
                                        ? "bg-gradient-to-t from-gray-900 to-transparent"
                                        : "bg-gradient-to-t from-white to-transparent"
                                )} />
                            )}
                        </div>

                        {/* Show More/Less button for long content */}
                        {content.length > 500 && (
                            <button
                                onClick={() => setIsContentExpanded(!isContentExpanded)}
                                className={cn(
                                    "mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-[11px] font-semibold transition-all duration-200",
                                    isDark
                                        ? "text-blue-400 hover:text-blue-300 bg-blue-950/30 hover:bg-blue-950/50 border border-blue-900/50"
                                        : "text-blue-600 hover:text-blue-700 bg-blue-50/50 hover:bg-blue-50 border border-blue-200/60"
                                )}
                            >
                                {isContentExpanded ? (
                                    <>
                                        <ChevronDown className="h-3.5 w-3.5" />
                                        Show Less
                                    </>
                                ) : (
                                    <>
                                        <ChevronRight className="h-3.5 w-3.5" />
                                        Show Full Content
                                    </>
                                )}
                            </button>
                        )}
                    </div>
                </div>
            )}


            {/* Raw JSON View - Collapsible (for debugging) */}
            <div className={cn(
                "border-t",
                isDark ? "border-gray-800/50" : "border-gray-100"
            )}>
                <button
                    onClick={() => setIsRawExpanded(!isRawExpanded)}
                    className={cn(
                        "w-full px-5 py-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider transition-all duration-200",
                        isDark
                            ? "text-gray-500 hover:text-gray-400 hover:bg-gray-900/30"
                            : "text-gray-500 hover:text-gray-600 hover:bg-gray-50/50"
                    )}
                >
                    {isRawExpanded ? (
                        <ChevronDown className="h-3 w-3" />
                    ) : (
                        <ChevronRight className="h-3 w-3" />
                    )}
                    View Raw Data
                </button>

                {isRawExpanded && (
                    <div className="px-4 pb-3">
                        <div className="relative">
                            <button
                                onClick={() => handleCopy(JSON.stringify(payload, null, 2), 'raw')}
                                className={cn(
                                    "absolute top-2 right-2 p-1 rounded transition-colors z-10",
                                    isDark
                                        ? "hover:bg-gray-800 text-gray-400"
                                        : "hover:bg-gray-100 text-gray-600"
                                )}
                            >
                                {copiedField === 'raw' ? (
                                    <Check className="h-3 w-3" />
                                ) : (
                                    <Copy className="h-3 w-3" />
                                )}
                            </button>
                            <SyntaxHighlighter
                                language="json"
                                style={syntaxStyle}
                                customStyle={{
                                    margin: 0,
                                    borderRadius: '0.375rem',
                                    fontSize: '0.65rem',
                                    padding: '0.75rem',
                                    background: isDark ? 'rgba(17, 24, 39, 0.8)' : 'rgba(249, 250, 251, 0.95)',
                                    maxHeight: '300px',
                                    overflow: 'auto'
                                }}
                            >
                                {JSON.stringify(payload, null, 2)}
                            </SyntaxHighlighter>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
