import { useState } from 'react';
import { apiClient } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Search, Copy, XCircle, Trash2, CalendarX } from 'lucide-react';
import { toast } from 'sonner';

interface SyncInfo {
    id: string;
    name: string;
    organization_id: string;
    status: string;
    readable_collection_id?: string;
    source_short_name?: string;
    source_is_authenticated?: boolean;
    total_entity_count?: number;
    total_arf_entity_count?: number;
    total_qdrant_entity_count?: number;
    total_vespa_entity_count?: number;
    last_job_status?: string;
    last_job_at?: string;
    created_at: string;
}

interface OrganizationMap {
    [key: string]: {
        name: string;
        id: string;
    };
}

interface OrganizationMetrics {
    id: string;
    name: string;
}

interface SyncFilters {
    syncIds: string;
    organizationId: string;
    collectionId: string;
    sourceType: string;
    status: string;
    isAuthenticated: string;
    limit: number;
}

export function SyncsTab() {
    const [syncs, setSyncs] = useState<SyncInfo[]>([]);
    const [isSyncsLoading, setIsSyncsLoading] = useState(false);
    const [syncFilters, setSyncFilters] = useState<SyncFilters>({
        syncIds: '',
        organizationId: '',
        collectionId: '',
        sourceType: '',
        status: 'all',
        isAuthenticated: 'all',
        limit: 100,
    });
    const [organizationMap, setOrganizationMap] = useState<OrganizationMap>({});

    const loadSyncs = async () => {
        setIsSyncsLoading(true);
        try {
            const params = new URLSearchParams();
            params.append('limit', syncFilters.limit.toString());

            if (syncFilters.syncIds.trim()) {
                params.append('sync_ids', syncFilters.syncIds.trim());
            }
            if (syncFilters.organizationId.trim()) {
                params.append('organization_id', syncFilters.organizationId.trim());
            }
            if (syncFilters.collectionId.trim()) {
                params.append('collection_id', syncFilters.collectionId.trim());
            }
            if (syncFilters.sourceType.trim()) {
                params.append('source_type', syncFilters.sourceType.trim());
            }
            if (syncFilters.status !== 'all') {
                params.append('status', syncFilters.status);
            }
            if (syncFilters.isAuthenticated !== 'all') {
                params.append('is_authenticated', syncFilters.isAuthenticated);
            }

            const response = await apiClient.get(`/admin/syncs?${params.toString()}`);

            if (!response.ok) {
                throw new Error(`Failed to load syncs: ${response.status}`);
            }

            const data = await response.json();
            setSyncs(data);

            const uniqueOrgIds = [...new Set(data.map((s: SyncInfo) => s.organization_id))] as string[];
            await fetchOrganizationNames(uniqueOrgIds);

            toast.success(`Loaded ${data.length} sync(s)`);
        } catch (error) {
            console.error('Failed to load syncs:', error);
            toast.error('Failed to load syncs');
            setSyncs([]);
        } finally {
            setIsSyncsLoading(false);
        }
    };

    const fetchOrganizationNames = async (orgIds: string[]) => {
        try {
            const response = await apiClient.get('/admin/organizations?limit=10000');
            if (response.ok) {
                const allOrgs = await response.json();
                const map: OrganizationMap = {};
                allOrgs.forEach((org: OrganizationMetrics) => {
                    map[org.id] = {
                        name: org.name,
                        id: org.id,
                    };
                });
                setOrganizationMap(map);
            }
        } catch (error) {
            console.error('Failed to fetch organization names:', error);
        }
    };

    const copyToClipboard = (text: string, label: string) => {
        navigator.clipboard.writeText(text);
        toast.success(`${label} copied to clipboard`);
    };

    const formatNumber = (num: number) => {
        return num.toLocaleString('en-US');
    };

    return (
        <>
            {/* Search Form */}
            <Card className="mb-6">
                <CardHeader>
                    <CardTitle>Search Syncs</CardTitle>
                    <CardDescription>
                        Find syncs across all organizations. Press Search to load results.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-1 gap-4 mb-4">
                        <div>
                            <Label htmlFor="sync-ids-filter">Sync ID(s)</Label>
                            <Input
                                id="sync-ids-filter"
                                placeholder="Comma-separated UUIDs (e.g., uuid1,uuid2,uuid3)"
                                value={syncFilters.syncIds}
                                onChange={(e) => setSyncFilters({ ...syncFilters, syncIds: e.target.value })}
                            />
                            <p className="text-xs text-muted-foreground mt-1">
                                Search by specific sync IDs. Leave empty to search all syncs.
                            </p>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                        <div>
                            <Label htmlFor="sync-org-filter">Organization ID</Label>
                            <Input
                                id="sync-org-filter"
                                placeholder="UUID or leave empty"
                                value={syncFilters.organizationId}
                                onChange={(e) => setSyncFilters({ ...syncFilters, organizationId: e.target.value })}
                            />
                        </div>
                        <div>
                            <Label htmlFor="sync-collection-filter">Collection ID</Label>
                            <Input
                                id="sync-collection-filter"
                                placeholder="Readable ID"
                                value={syncFilters.collectionId}
                                onChange={(e) => setSyncFilters({ ...syncFilters, collectionId: e.target.value })}
                            />
                        </div>
                        <div>
                            <Label htmlFor="sync-source-filter">Source Type</Label>
                            <Input
                                id="sync-source-filter"
                                placeholder="e.g., linear, github"
                                value={syncFilters.sourceType}
                                onChange={(e) => setSyncFilters({ ...syncFilters, sourceType: e.target.value })}
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                        <div>
                            <Label htmlFor="sync-status-filter">Sync Status</Label>
                            <Select
                                value={syncFilters.status}
                                onValueChange={(value) => setSyncFilters({ ...syncFilters, status: value })}
                            >
                                <SelectTrigger id="sync-status-filter">
                                    <SelectValue placeholder="All statuses" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All</SelectItem>
                                    <SelectItem value="active">Active</SelectItem>
                                    <SelectItem value="inactive">Inactive</SelectItem>
                                    <SelectItem value="error">Error</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label htmlFor="sync-auth-filter">Authentication</Label>
                            <Select
                                value={syncFilters.isAuthenticated}
                                onValueChange={(value) => setSyncFilters({ ...syncFilters, isAuthenticated: value })}
                            >
                                <SelectTrigger id="sync-auth-filter">
                                    <SelectValue placeholder="All" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All</SelectItem>
                                    <SelectItem value="true">Authenticated</SelectItem>
                                    <SelectItem value="false">Needs Reauth</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label htmlFor="sync-limit">Results Limit</Label>
                            <Input
                                id="sync-limit"
                                type="number"
                                min="10"
                                max="500"
                                value={syncFilters.limit}
                                onChange={(e) => setSyncFilters({ ...syncFilters, limit: parseInt(e.target.value) || 100 })}
                            />
                        </div>
                    </div>

                    <div className="flex gap-2">
                        <Button onClick={loadSyncs} disabled={isSyncsLoading} className="gap-2">
                            <Search className="h-4 w-4" />
                            {isSyncsLoading ? 'Searching...' : 'Search'}
                        </Button>
                        {syncs.length > 0 && (
                            <Button variant="outline" onClick={() => setSyncs([])}>
                                Clear Results
                            </Button>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Stats Cards */}
            {syncs.length > 0 && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                    <Card>
                        <CardHeader className="pb-2 pt-3">
                            <CardTitle className="text-xs font-medium text-muted-foreground">
                                Total Syncs
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pb-3">
                            <div className="text-2xl font-bold">{syncs.length}</div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2 pt-3">
                            <CardTitle className="text-xs font-medium text-muted-foreground">
                                Active
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pb-3">
                            <div className="text-2xl font-bold text-green-500">
                                {syncs.filter(s => s.status === 'active').length}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2 pt-3">
                            <CardTitle className="text-xs font-medium text-muted-foreground">
                                Total Entities
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pb-3">
                            <div className="text-2xl font-bold">
                                {formatNumber(syncs.reduce((sum, s) => sum + (s.total_entity_count || 0), 0))}
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader className="pb-2 pt-3">
                            <CardTitle className="text-xs font-medium text-muted-foreground">
                                Needs Reauth
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="pb-3">
                            <div className="text-2xl font-bold text-amber-500">
                                {syncs.filter(s => s.source_is_authenticated === false).length}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Results Table */}
            {syncs.length > 0 && (
                <Card>
                    <CardHeader>
                        <CardTitle>Sync Results ({syncs.length})</CardTitle>
                        <CardDescription>
                            Showing syncs matching your search criteria
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Sync Name / ID</TableHead>
                                        <TableHead>Organization</TableHead>
                                        <TableHead>Collection</TableHead>
                                        <TableHead>Source</TableHead>
                                        <TableHead>Status</TableHead>
                                        <TableHead>Auth</TableHead>
                                        <TableHead className="text-right">Entity Counts</TableHead>
                                        <TableHead>Last Job</TableHead>
                                        <TableHead>Actions</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {syncs.map((sync) => {
                                        const orgInfo = organizationMap[sync.organization_id];
                                        return (
                                            <TableRow key={sync.id}>
                                                <TableCell className="font-medium">
                                                    <div className="flex flex-col gap-1">
                                                        <span className="truncate max-w-[200px]">{sync.name}</span>
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-xs text-muted-foreground font-mono">
                                                                {sync.id}
                                                            </span>
                                                            <button
                                                                onClick={() => copyToClipboard(sync.id, 'Sync ID')}
                                                                className="text-muted-foreground hover:text-foreground transition-colors"
                                                            >
                                                                <Copy className="h-3 w-3" />
                                                            </button>
                                                        </div>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex flex-col gap-1">
                                                        <span className="text-sm font-medium">
                                                            {orgInfo?.name || 'Unknown'}
                                                        </span>
                                                        <div className="flex items-center gap-1">
                                                            <span className="text-xs text-muted-foreground font-mono">
                                                                {sync.organization_id}
                                                            </span>
                                                            <button
                                                                onClick={() => copyToClipboard(sync.organization_id, 'Organization ID')}
                                                                className="text-muted-foreground hover:text-foreground transition-colors"
                                                            >
                                                                <Copy className="h-3 w-3" />
                                                            </button>
                                                        </div>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <span className="text-sm">{sync.readable_collection_id || '-'}</span>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="outline">{sync.source_short_name || 'Unknown'}</Badge>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge
                                                        variant={sync.status === 'active' ? 'default' : 'secondary'}
                                                        className={sync.status === 'active' ? 'bg-green-500/20 text-green-400 border-green-500/30' : ''}
                                                    >
                                                        {sync.status}
                                                    </Badge>
                                                </TableCell>
                                                <TableCell>
                                                    {sync.source_is_authenticated === true && (
                                                        <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/30">
                                                            ✓
                                                        </Badge>
                                                    )}
                                                    {sync.source_is_authenticated === false && (
                                                        <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/30">
                                                            ✗
                                                        </Badge>
                                                    )}
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <div className="flex flex-col gap-1 items-end text-xs font-mono">
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-muted-foreground">PG:</span>
                                                            <span>{formatNumber(sync.total_entity_count || 0)}</span>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-muted-foreground">ARF:</span>
                                                            <span>{sync.total_arf_entity_count !== null && sync.total_arf_entity_count !== undefined ? formatNumber(sync.total_arf_entity_count) : '-'}</span>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-muted-foreground">Qdrant:</span>
                                                            <span>{sync.total_qdrant_entity_count !== null && sync.total_qdrant_entity_count !== undefined ? formatNumber(sync.total_qdrant_entity_count) : '-'}</span>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                            <span className="text-muted-foreground">Vespa:</span>
                                                            <span>{sync.total_vespa_entity_count !== null && sync.total_vespa_entity_count !== undefined ? formatNumber(sync.total_vespa_entity_count) : '-'}</span>
                                                        </div>
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    {sync.last_job_status && (
                                                        <div className="flex flex-col gap-1">
                                                            <Badge
                                                                variant="outline"
                                                                className={
                                                                    sync.last_job_status === 'completed'
                                                                        ? 'bg-green-500/10 text-green-400 border-green-500/30'
                                                                        : sync.last_job_status === 'failed'
                                                                            ? 'bg-red-500/10 text-red-400 border-red-500/30'
                                                                            : sync.last_job_status === 'running'
                                                                                ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                                                                                : ''
                                                                }
                                                            >
                                                                {sync.last_job_status}
                                                            </Badge>
                                                            {sync.last_job_at && (
                                                                <span className="text-xs text-muted-foreground">
                                                                    {new Date(sync.last_job_at).toLocaleString()}
                                                                </span>
                                                            )}
                                                        </div>
                                                    )}
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex gap-1">
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            disabled
                                                            className="h-7 px-2"
                                                            title="Cancel sync job"
                                                        >
                                                            <XCircle className="h-3.5 w-3.5" />
                                                        </Button>
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            disabled
                                                            className="h-7 px-2"
                                                            title="Deschedule sync"
                                                        >
                                                            <CalendarX className="h-3.5 w-3.5" />
                                                        </Button>
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            disabled
                                                            className="h-7 px-2"
                                                            title="Delete sync"
                                                        >
                                                            <Trash2 className="h-3.5 w-3.5" />
                                                        </Button>
                                                    </div>
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                </TableBody>
                            </Table>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Empty State */}
            {syncs.length === 0 && !isSyncsLoading && (
                <Card>
                    <CardContent className="py-12">
                        <div className="text-center text-muted-foreground">
                            <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
                            <p>No syncs loaded. Use the search form above to find syncs.</p>
                        </div>
                    </CardContent>
                </Card>
            )}
        </>
    );
}

