import { useState, useEffect } from 'react';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Save, Trash2, Building2, User, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api';

interface SourceRateLimitRow {
    source_short_name: string;
    rate_limit_level: 'org' | 'connection' | null;
    limit: number | null;
    window_seconds: number | null;
    id: string | null;
}

export const SourceRateLimits = () => {
    const [limits, setLimits] = useState<SourceRateLimitRow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [editingRows, setEditingRows] = useState<
        Map<string, { limit: string; window: string }>
    >(new Map());
    const [savingRows, setSavingRows] = useState<Set<string>>(new Set());

    // Separate state for Pipedream proxy
    const [pipedreamLimit, setPipedreamLimit] = useState<string>('1000');
    const [pipedreamWindow, setPipedreamWindow] = useState<string>('300');
    const [pipedreamId, setPipedreamId] = useState<string | null>(null);
    const [originalPipedreamLimit, setOriginalPipedreamLimit] = useState<string>('1000');
    const [originalPipedreamWindow, setOriginalPipedreamWindow] = useState<string>('300');
    const [isSavingPipedream, setIsSavingPipedream] = useState(false);

    useEffect(() => {
        fetchLimits();
    }, []);

    const fetchLimits = async () => {
        try {
            setIsLoading(true);
            const response = await apiClient.get('/source-rate-limits');

            if (!response.ok) {
                throw new Error('Failed to fetch rate limits');
            }

            const data = await response.json();

            // Extract Pipedream proxy (first item)
            if (data.length > 0 && data[0].source_short_name === 'pipedream_proxy') {
                const pipedream = data[0];
                setPipedreamLimit(String(pipedream.limit));
                setPipedreamWindow(String(pipedream.window_seconds));
                setOriginalPipedreamLimit(String(pipedream.limit));
                setOriginalPipedreamWindow(String(pipedream.window_seconds));
                setPipedreamId(pipedream.id);
                setLimits(data.slice(1)); // Rest are regular sources
            } else {
                setLimits(data);
            }
        } catch (error) {
            toast.error('Failed to load rate limits');
            console.error(error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleEditChange = (
        sourceShortName: string,
        field: 'limit' | 'window',
        value: string
    ) => {
        const current = editingRows.get(sourceShortName) || {
            limit: '',
            window: '',
        };

        // Find the row to get current values
        const row = limits.find((r) => r.source_short_name === sourceShortName);
        if (!row) return;

        const newValues = {
            limit: field === 'limit' ? value : current.limit || String(row.limit || ''),
            window: field === 'window' ? value : current.window || String(row.window_seconds || ''),
        };

        setEditingRows(new Map(editingRows.set(sourceShortName, newValues)));
    };

    const handleSaveRow = async (sourceShortName: string) => {
        const edited = editingRows.get(sourceShortName);
        if (!edited) return;

        const limit = parseInt(edited.limit);
        const windowSeconds = parseInt(edited.window);

        if (isNaN(limit) || isNaN(windowSeconds) || limit <= 0 || windowSeconds <= 0) {
            toast.error('Please enter both limit and window (positive numbers required)');
            return;
        }

        try {
            setSavingRows(new Set(savingRows.add(sourceShortName)));

            const response = await apiClient.put(`/source-rate-limits/${sourceShortName}`, undefined, {
                limit,
                window_seconds: windowSeconds,
            });

            if (!response.ok) {
                throw new Error('Failed to update rate limit');
            }

            toast.success(`Updated ${sourceShortName} rate limit`);
            fetchLimits(); // Refresh
            editingRows.delete(sourceShortName);
            setEditingRows(new Map(editingRows));
        } catch (error) {
            toast.error('Failed to update rate limit');
            console.error(error);
        } finally {
            setSavingRows((prev) => {
                const newSet = new Set(prev);
                newSet.delete(sourceShortName);
                return newSet;
            });
        }
    };

    const handleDeleteRow = async (sourceShortName: string) => {
        try {
            setSavingRows(new Set(savingRows.add(sourceShortName)));

            const response = await apiClient.delete(`/source-rate-limits/${sourceShortName}`);

            if (!response.ok) {
                throw new Error('Failed to remove rate limit');
            }

            toast.success(`Removed ${sourceShortName} rate limit`);
            fetchLimits();
            editingRows.delete(sourceShortName);
            setEditingRows(new Map(editingRows));
        } catch (error) {
            toast.error('Failed to remove rate limit');
            console.error(error);
        } finally {
            setSavingRows((prev) => {
                const newSet = new Set(prev);
                newSet.delete(sourceShortName);
                return newSet;
            });
        }
    };

    const handleSavePipedream = async () => {
        const limit = parseInt(pipedreamLimit);
        const windowSeconds = parseInt(pipedreamWindow);

        if (isNaN(limit) || isNaN(windowSeconds) || limit <= 0 || windowSeconds <= 0) {
            toast.error('Please enter valid positive numbers');
            return;
        }

        try {
            setIsSavingPipedream(true);

            const response = await apiClient.put('/source-rate-limits/pipedream_proxy', undefined, {
                limit,
                window_seconds: windowSeconds,
            });

            if (!response.ok) {
                throw new Error('Failed to update Pipedream proxy limit');
            }

            toast.success('Updated Pipedream proxy limit');
            setOriginalPipedreamLimit(String(limit));
            setOriginalPipedreamWindow(String(windowSeconds));
            fetchLimits();
        } catch (error) {
            toast.error('Failed to update Pipedream proxy limit');
            console.error(error);
        } finally {
            setIsSavingPipedream(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Pipedream Proxy Card */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Pipedream Proxy Limit
                    </CardTitle>
                    <CardDescription>
                        Organization-wide limit for all API requests through Pipedream proxy. Applies when using
                        Pipedream auth provider with default OAuth.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="flex items-end gap-4">
                        <div className="flex-1 max-w-xs">
                            <Label htmlFor="pipedream-limit">Requests per 5 minutes</Label>
                            <Input
                                id="pipedream-limit"
                                type="number"
                                value={pipedreamLimit}
                                onChange={(e) => setPipedreamLimit(e.target.value)}
                                placeholder="1000"
                                min="1"
                                className="mt-1.5"
                            />
                        </div>
                        <div className="flex gap-2">
                            <Button
                                onClick={handleSavePipedream}
                                disabled={
                                    isSavingPipedream ||
                                    (pipedreamLimit === originalPipedreamLimit && pipedreamWindow === originalPipedreamWindow)
                                }
                                size="sm"
                                className="h-10"
                            >
                                {isSavingPipedream ? (
                                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                    <Save className="h-4 w-4 mr-2" />
                                )}
                                Save
                            </Button>
                            {pipedreamId && (
                                <Button
                                    onClick={async () => {
                                        await handleDeleteRow('pipedream_proxy');
                                        // Reset to defaults
                                        setPipedreamLimit('1000');
                                        setPipedreamWindow('300');
                                        setOriginalPipedreamLimit('1000');
                                        setOriginalPipedreamWindow('300');
                                    }}
                                    disabled={isSavingPipedream}
                                    size="sm"
                                    variant="ghost"
                                    className="h-10"
                                >
                                    Restore Default
                                </Button>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Sources Table Card */}
            <Card>
                <CardHeader>
                    <CardTitle>Source-Specific Rate Limits</CardTitle>
                    <CardDescription>
                        Configure rate limits per source to prevent exhausting API quotas. Limits apply to all users in
                        your organization.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Source</TableHead>
                                <TableHead>Tracking Level</TableHead>
                                <TableHead>Limit (requests)</TableHead>
                                <TableHead>Window (seconds)</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {limits.map((row) => {
                                const isEditing = editingRows.has(row.source_short_name);
                                const isSaving = savingRows.has(row.source_short_name);
                                const edited = editingRows.get(row.source_short_name);

                                return (
                                    <TableRow key={row.source_short_name}>
                                        <TableCell className="font-medium capitalize">
                                            {row.source_short_name}
                                        </TableCell>
                                        <TableCell>
                                            {row.rate_limit_level === 'org' && (
                                                <Badge variant="secondary" className="gap-1">
                                                    <Building2 className="h-3 w-3" />
                                                    Organization-wide
                                                </Badge>
                                            )}
                                            {row.rate_limit_level === 'connection' && (
                                                <Badge variant="outline" className="gap-1">
                                                    <User className="h-3 w-3" />
                                                    Per Connection
                                                </Badge>
                                            )}
                                            {!row.rate_limit_level && (
                                                <span className="text-muted-foreground text-sm">Not supported</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            {row.rate_limit_level ? (
                                                <Input
                                                    type="number"
                                                    placeholder="e.g. 800"
                                                    value={edited?.limit ?? row.limit ?? ''}
                                                    onChange={(e) =>
                                                        handleEditChange(row.source_short_name, 'limit', e.target.value)
                                                    }
                                                    className="w-28"
                                                    min="1"
                                                    disabled={isSaving}
                                                />
                                            ) : (
                                                <span className="text-muted-foreground">-</span>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            {row.rate_limit_level ? (
                                                <Input
                                                    type="number"
                                                    placeholder="e.g. 60"
                                                    value={edited?.window ?? row.window_seconds ?? ''}
                                                    onChange={(e) =>
                                                        handleEditChange(row.source_short_name, 'window', e.target.value)
                                                    }
                                                    className="w-28"
                                                    min="1"
                                                    disabled={isSaving}
                                                />
                                            ) : (
                                                <span className="text-muted-foreground">-</span>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {row.rate_limit_level && (
                                                <div className="flex justify-end gap-2">
                                                    <Button
                                                        size="sm"
                                                        onClick={() => handleSaveRow(row.source_short_name)}
                                                        disabled={
                                                            isSaving ||
                                                            // Disabled if no edits OR if values match DB
                                                            (!isEditing || (
                                                                edited &&
                                                                edited.limit === (row.limit !== null ? String(row.limit) : '') &&
                                                                edited.window === (row.window_seconds !== null ? String(row.window_seconds) : '')
                                                            ))
                                                        }
                                                    >
                                                        {isSaving ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <Save className="h-4 w-4" />
                                                        )}
                                                    </Button>
                                                    <Button
                                                        size="sm"
                                                        variant="ghost"
                                                        onClick={() => handleDeleteRow(row.source_short_name)}
                                                        disabled={isSaving || !row.id}
                                                    >
                                                        {isSaving ? (
                                                            <Loader2 className="h-4 w-4 animate-spin" />
                                                        ) : (
                                                            <Trash2 className="h-4 w-4" />
                                                        )}
                                                    </Button>
                                                </div>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                );
                            })}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
};

