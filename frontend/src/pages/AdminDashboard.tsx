import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/lib/auth-context';
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Shield, Plus, Crown, Building2, ArrowUpCircle, UserPlus, Search, ArrowUpDown, Users, Database, Activity, Flag, Copy, XCircle, Trash2, CalendarX } from 'lucide-react';
import { toast } from 'sonner';

interface AvailableFeatureFlag {
  name: string;
  value: string;
}

interface OrganizationMetrics {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  modified_at: string;
  auth0_org_id?: string;
  billing_plan?: string;
  billing_status?: string;
  stripe_customer_id?: string;
  trial_ends_at?: string;
  user_count: number;
  source_connection_count: number;
  entity_count: number;
  query_count: number;
  last_active_at?: string;
  is_member: boolean;
  member_role?: string;
  enabled_features?: string[];
}

type SortField = 'name' | 'created_at' | 'billing_plan' | 'user_count' | 'source_connection_count' | 'entity_count' | 'query_count' | 'last_active_at' | 'is_member';
type SortOrder = 'asc' | 'desc';
type MembershipFilter = 'all' | 'member' | 'non-member';

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

interface SyncFilters {
  syncIds: string;
  organizationId: string;
  collectionId: string;
  sourceType: string;
  status: string;
  isAuthenticated: string;
  limit: number;
}

export function AdminDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [organizations, setOrganizations] = useState<OrganizationMetrics[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedOrg, setSelectedOrg] = useState<OrganizationMetrics | null>(null);
  const [actionType, setActionType] = useState<'join' | 'upgrade' | 'create' | 'feature-flags' | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Syncs state
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

  // Feature flags state
  const [availableFeatureFlags, setAvailableFeatureFlags] = useState<AvailableFeatureFlag[]>([]);
  const [enabledFeatureFlags, setEnabledFeatureFlags] = useState<string[]>([]);

  // Search and sort state
  const [searchTerm, setSearchTerm] = useState('');
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');
  const [membershipFilter, setMembershipFilter] = useState<MembershipFilter>('all');

  // Create enterprise org form
  const [newOrgName, setNewOrgName] = useState('');
  const [newOrgDescription, setNewOrgDescription] = useState('');
  const [ownerEmail, setOwnerEmail] = useState('');

  // Join org form
  const [selectedRole, setSelectedRole] = useState<'owner' | 'admin' | 'member'>('owner');

  useEffect(() => {
    // Redirect if not admin
    if (user && !user.is_admin) {
      toast.error('Admin access required');
      navigate('/');
      return;
    }

    if (user?.is_admin) {
      loadOrganizations();
      loadAvailableFeatureFlags();
    }
  }, [user, navigate]);

  const loadAvailableFeatureFlags = async () => {
    try {
      const response = await apiClient.get('/admin/feature-flags');
      if (response.ok) {
        const flags = await response.json();
        setAvailableFeatureFlags(flags);
      } else {
        throw new Error('Failed to load available feature flags');
      }
    } catch (error) {
      console.error('Failed to load available feature flags:', error);
      // Don't show error toast, this is not critical
    }
  };

  const loadSyncs = async () => {
    setIsSyncsLoading(true);
    try {
      // Build query parameters
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

      // Fetch organization names for unique org IDs
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
      // Fetch all orgs and build a map
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

  const loadOrganizations = async () => {
    try {
      setIsLoading(true);
      // Fetch all organizations with comprehensive metrics
      const params = new URLSearchParams({
        limit: '10000',
        sort_by: sortField,
        sort_order: sortOrder,
      });

      if (searchTerm) {
        params.set('search', searchTerm);
      }

      const response = await apiClient.get(`/admin/organizations?${params.toString()}`);
      if (response.ok) {
        const data = await response.json();
        setOrganizations(data);
      } else {
        throw new Error('Failed to load organizations');
      }
    } catch (error) {
      console.error('Failed to load organizations:', error);
      toast.error('Failed to load organizations');
    } finally {
      setIsLoading(false);
    }
  };

  // Reload when search/sort changes (debounced search)
  useEffect(() => {
    if (!user?.is_admin) return;

    const timer = setTimeout(() => {
      loadOrganizations();
    }, searchTerm ? 300 : 0);

    return () => clearTimeout(timer);
  }, [searchTerm, sortField, sortOrder]);

  // Filter and sort organizations (membership-based operations done client-side)
  const filteredOrganizations = useMemo(() => {
    let filtered = organizations;

    // Apply membership filter
    if (membershipFilter === 'member') {
      filtered = filtered.filter(org => org.is_member);
    } else if (membershipFilter === 'non-member') {
      filtered = filtered.filter(org => !org.is_member);
    }

    // Apply client-side sorting if sorting by membership (not handled by backend)
    if (sortField === 'is_member') {
      filtered = [...filtered].sort((a, b) => {
        const aValue = a.is_member ? 1 : 0;
        const bValue = b.is_member ? 1 : 0;
        return sortOrder === 'asc' ? aValue - bValue : bValue - aValue;
      });
    }

    return filtered;
  }, [organizations, membershipFilter, sortField, sortOrder]);

  // Calculate aggregate stats
  const stats = useMemo(() => {
    return {
      totalOrgs: organizations.length,
      totalUsers: organizations.reduce((sum, org) => sum + org.user_count, 0),
      totalSourceConnections: organizations.reduce((sum, org) => sum + org.source_connection_count, 0),
      totalEntities: organizations.reduce((sum, org) => sum + org.entity_count, 0),
      enterpriseCount: organizations.filter(org => org.billing_plan === 'enterprise').length,
      trialCount: organizations.filter(org => org.billing_plan === 'trial').length,
      memberCount: organizations.filter(org => org.is_member).length,
    };
  }, [organizations]);

  const handleJoinOrg = async () => {
    if (!selectedOrg) return;

    try {
      setIsSubmitting(true);
      const response = await apiClient.post(
        `/admin/organizations/${selectedOrg.id}/add-self?role=${selectedRole}`
      );

      if (response.ok) {
        toast.success(`Successfully joined ${selectedOrg.name} as ${selectedRole}`);
        setActionType(null);
        setSelectedOrg(null);
        loadOrganizations();
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to join organization');
      }
    } catch (error: any) {
      console.error('Failed to join organization:', error);
      toast.error(error.message || 'Failed to join organization');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpgradeToEnterprise = async () => {
    if (!selectedOrg) return;

    try {
      setIsSubmitting(true);
      const response = await apiClient.post(
        `/admin/organizations/${selectedOrg.id}/upgrade-to-enterprise`
      );

      if (response.ok) {
        toast.success(`Successfully upgraded ${selectedOrg.name} to Enterprise`);
        setActionType(null);
        setSelectedOrg(null);
        loadOrganizations();
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to upgrade organization');
      }
    } catch (error: any) {
      console.error('Failed to upgrade organization:', error);
      toast.error(error.message || 'Failed to upgrade organization');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateEnterpriseOrg = async () => {
    if (!newOrgName || !ownerEmail) {
      toast.error('Organization name and owner email are required');
      return;
    }

    try {
      setIsSubmitting(true);
      const response = await apiClient.post('/admin/organizations/create-enterprise', {
        name: newOrgName,
        description: newOrgDescription,
        owner_email: ownerEmail,
      });

      if (response.ok) {
        toast.success(`Successfully created enterprise organization ${newOrgName}`);
        setActionType(null);
        setNewOrgName('');
        setNewOrgDescription('');
        setOwnerEmail('');
        loadOrganizations();
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create organization');
      }
    } catch (error: any) {
      console.error('Failed to create organization:', error);
      toast.error(error.message || 'Failed to create organization');
    } finally {
      setIsSubmitting(false);
    }
  };

  const loadFeatureFlags = (org: OrganizationMetrics) => {
    // Feature flags are already loaded from the organization data
    setEnabledFeatureFlags(org.enabled_features || []);
  };

  const handleToggleFeatureFlag = async (flag: string, currentlyEnabled: boolean) => {
    if (!selectedOrg) return;

    try {
      const action = currentlyEnabled ? 'disable' : 'enable';
      const response = await apiClient.post(
        `/admin/organizations/${selectedOrg.id}/feature-flags/${flag}/${action}`
      );

      if (response.ok) {
        toast.success(`Feature ${flag} ${currentlyEnabled ? 'disabled' : 'enabled'}`);
        // Update local state
        if (currentlyEnabled) {
          setEnabledFeatureFlags(enabledFeatureFlags.filter(f => f !== flag));
        } else {
          setEnabledFeatureFlags([...enabledFeatureFlags, flag]);
        }
        // Reload organizations to get fresh data
        loadOrganizations();
      } else {
        const error = await response.json();
        throw new Error(error.detail || `Failed to ${action} feature flag`);
      }
    } catch (error: any) {
      console.error('Failed to toggle feature flag:', error);
      toast.error(error.message || 'Failed to update feature flag');
    }
  };

  const openFeatureFlagsDialog = (org: OrganizationMetrics) => {
    setSelectedOrg(org);
    setActionType('feature-flags');
    loadFeatureFlags(org);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatNumber = (num: number) => {
    return num.toLocaleString('en-US');
  };

  const getBillingPlanBadge = (plan?: string) => {
    if (!plan) return <Badge variant="outline">None</Badge>;

    const variants: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline', className?: string }> = {
      enterprise: { variant: 'default', className: 'bg-brand-lime/20 text-brand-lime border-brand-lime/30' },
      pro: { variant: 'default', className: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
      starter: { variant: 'secondary' },
      trial: { variant: 'outline' },
    };

    const config = variants[plan] || { variant: 'outline' };
    return <Badge variant={config.variant} className={config.className}>{plan}</Badge>;
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      // Toggle order if same field
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc'); // Default to desc for new field
    }
  };

  if (!user?.is_admin) {
    return null;
  }

  return (
    <div className="container mx-auto py-6 px-4 max-w-[1800px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Shield className="h-8 w-8 text-primary" />
          <div>
            <h1 className="text-3xl font-bold">Admin Dashboard</h1>
            <p className="text-muted-foreground">Manage organizations and syncs across the platform</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="organizations" className="w-full">
        <TabsList className="mb-6">
          <TabsTrigger value="organizations" className="gap-2">
            <Building2 className="h-4 w-4" />
            Organizations
          </TabsTrigger>
          <TabsTrigger value="syncs" className="gap-2">
            <Activity className="h-4 w-4" />
            Syncs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="organizations" className="mt-0">
          <div className="flex items-center justify-end mb-6">
            <Button
              onClick={() => {
                setActionType('create');
                setNewOrgName('');
                setNewOrgDescription('');
                setOwnerEmail('');
              }}
              className="gap-2"
            >
              <Plus className="h-4 w-4" />
              Create Enterprise Org
            </Button>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
            <Card className="border-l-4 border-l-brand-lime/50">
              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-2">
                  <Building2 className="h-3.5 w-3.5" />
                  Organizations
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="text-2xl font-bold">{formatNumber(stats.totalOrgs)}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {stats.enterpriseCount} enterprise • {stats.trialCount} trial
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-2">
                  <Users className="h-3.5 w-3.5" />
                  Total Users
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="text-2xl font-bold">{formatNumber(stats.totalUsers)}</div>
                <p className="text-xs text-muted-foreground mt-1">Across all orgs</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-2">
                  <Database className="h-3.5 w-3.5" />
                  Connections
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="text-2xl font-bold">{formatNumber(stats.totalSourceConnections)}</div>
                <p className="text-xs text-muted-foreground mt-1">Source connections</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-2">
                  <Activity className="h-3.5 w-3.5" />
                  Entities
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="text-2xl font-bold">{formatNumber(stats.totalEntities)}</div>
                <p className="text-xs text-muted-foreground mt-1">Total indexed</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Admin User
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="text-sm font-medium truncate">{user.email}</div>
                <Badge variant="outline" className="mt-1 text-xs">Admin</Badge>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 pt-3">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  Platform
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-3">
                <div className="text-sm font-medium">Airweave</div>
                <p className="text-xs text-muted-foreground mt-1">Admin Panel</p>
              </CardContent>
            </Card>
          </div>

          {/* Organizations Table */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>All Organizations</CardTitle>
                  <CardDescription>
                    View and manage all organizations on the platform
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Select value={membershipFilter} onValueChange={(value: MembershipFilter) => setMembershipFilter(value)}>
                    <SelectTrigger className="w-[180px]">
                      <SelectValue placeholder="Filter by membership" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Organizations</SelectItem>
                      <SelectItem value="member">Member ({stats.memberCount})</SelectItem>
                      <SelectItem value="non-member">Non-member ({stats.totalOrgs - stats.memberCount})</SelectItem>
                    </SelectContent>
                  </Select>
                  <div className="relative w-72">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search organizations..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-8"
                    />
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {isLoading ? (
                <div className="text-center py-12 text-muted-foreground">Loading organizations...</div>
              ) : filteredOrganizations.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  {searchTerm ? 'No organizations match your search' :
                    membershipFilter !== 'all' ? `No ${membershipFilter === 'member' ? 'member' : 'non-member'} organizations found` :
                      'No organizations found'}
                </div>
              ) : (
                <div className="border-t">
                  <Table>
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="w-[220px]">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -ml-3 data-[state=open]:bg-accent"
                            onClick={() => handleSort('name')}
                          >
                            Organization
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[120px]">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -ml-3"
                            onClick={() => handleSort('billing_plan')}
                          >
                            Plan
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[110px]">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -ml-3"
                            onClick={() => handleSort('is_member')}
                          >
                            Membership
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[100px] text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -mr-3"
                            onClick={() => handleSort('user_count')}
                          >
                            Users
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[120px] text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -mr-3"
                            onClick={() => handleSort('source_connection_count')}
                          >
                            Connections
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[110px] text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -mr-3"
                            onClick={() => handleSort('entity_count')}
                          >
                            Entities
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[100px] text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -mr-3"
                            onClick={() => handleSort('query_count')}
                          >
                            Queries
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[130px]">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -ml-3"
                            onClick={() => handleSort('last_active_at')}
                          >
                            Last Active
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="w-[130px]">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 -ml-3"
                            onClick={() => handleSort('created_at')}
                          >
                            Created
                            <ArrowUpDown className="ml-2 h-3 w-3" />
                          </Button>
                        </TableHead>
                        <TableHead className="text-right w-[200px]">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredOrganizations.map((org) => (
                        <TableRow key={org.id} className="hover:bg-muted/30">
                          <TableCell className="py-2">
                            <div className="flex items-center gap-2">
                              <Building2 className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                              <div className="min-w-0 flex-1">
                                <div className="font-medium truncate">{org.name}</div>
                                {org.description && (
                                  <div className="text-xs text-muted-foreground truncate">
                                    {org.description}
                                  </div>
                                )}
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="py-2">
                            {getBillingPlanBadge(org.billing_plan)}
                          </TableCell>
                          <TableCell className="py-2">
                            {org.is_member ? (
                              <Badge variant="outline" className="text-xs px-2 py-0.5 h-5 gap-1">
                                {org.member_role === 'owner' && <Crown className="h-3 w-3 text-brand-lime/90" />}
                                {org.member_role === 'admin' && <Shield className="h-3 w-3 text-brand-lime/90" />}
                                {org.member_role}
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right py-2 font-mono text-sm">
                            {formatNumber(org.user_count)}
                          </TableCell>
                          <TableCell className="text-right py-2 font-mono text-sm">
                            {formatNumber(org.source_connection_count)}
                          </TableCell>
                          <TableCell className="text-right py-2 font-mono text-sm">
                            {formatNumber(org.entity_count)}
                          </TableCell>
                          <TableCell className="text-right py-2 font-mono text-sm">
                            {formatNumber(org.query_count)}
                          </TableCell>
                          <TableCell className="py-2 text-xs text-muted-foreground">
                            {org.last_active_at ? formatDate(org.last_active_at) : '—'}
                          </TableCell>
                          <TableCell className="py-2 text-xs text-muted-foreground">
                            {formatDate(org.created_at)}
                          </TableCell>
                          <TableCell className="text-right py-2">
                            <div className="flex justify-end gap-1.5">
                              {org.is_member ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled
                                  className="h-7 gap-1.5 text-xs text-muted-foreground"
                                >
                                  <UserPlus className="h-3 w-3" />
                                  Member
                                </Button>
                              ) : (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    setSelectedOrg(org);
                                    setActionType('join');
                                    setSelectedRole('owner');
                                  }}
                                  className="h-7 gap-1.5 text-xs"
                                >
                                  <UserPlus className="h-3 w-3" />
                                  Join
                                </Button>
                              )}
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => openFeatureFlagsDialog(org)}
                                className="h-7 gap-1.5 text-xs"
                              >
                                <Flag className="h-3 w-3" />
                                Features
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setSelectedOrg(org);
                                  setActionType('upgrade');
                                }}
                                className="h-7 gap-1.5 text-xs"
                              >
                                <ArrowUpCircle className="h-3 w-3" />
                                Upgrade
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="syncs" className="mt-0">
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
        </TabsContent>
      </Tabs>

      {/* Join Organization Dialog */}
      <Dialog open={actionType === 'join'} onOpenChange={(open) => !open && setActionType(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Join Organization</DialogTitle>
            <DialogDescription>
              Add yourself to {selectedOrg?.name} with a specific role
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="role">Role</Label>
              <Select value={selectedRole} onValueChange={(value: any) => setSelectedRole(value)}>
                <SelectTrigger>
                  <SelectValue placeholder="Select role" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="owner">
                    <div className="flex items-center gap-2">
                      <Crown className="h-4 w-4 text-brand-lime/90" />
                      Owner
                    </div>
                  </SelectItem>
                  <SelectItem value="admin">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-brand-lime/90" />
                      Admin
                    </div>
                  </SelectItem>
                  <SelectItem value="member">Member</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setActionType(null)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleJoinOrg} disabled={isSubmitting}>
              {isSubmitting ? 'Joining...' : 'Join Organization'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Upgrade to Enterprise Dialog */}
      <Dialog open={actionType === 'upgrade'} onOpenChange={(open) => !open && setActionType(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upgrade to Enterprise</DialogTitle>
            <DialogDescription>
              Upgrade {selectedOrg?.name} to an Enterprise plan. This will bypass Stripe and set the organization directly to enterprise.
            </DialogDescription>
          </DialogHeader>

          <div className="bg-muted/50 p-4 rounded-lg my-4">
            <p className="text-sm text-muted-foreground">
              This action will:
            </p>
            <ul className="list-disc list-inside text-sm text-muted-foreground mt-2 space-y-1">
              <li>Set the billing plan to "enterprise"</li>
              <li>Remove subscription limits</li>
              <li>Create or update billing record</li>
            </ul>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setActionType(null)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleUpgradeToEnterprise} disabled={isSubmitting}>
              {isSubmitting ? 'Upgrading...' : 'Confirm Upgrade'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Enterprise Organization Dialog */}
      <Dialog open={actionType === 'create'} onOpenChange={(open) => !open && setActionType(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Enterprise Organization</DialogTitle>
            <DialogDescription>
              Create a new organization directly on the Enterprise plan
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="orgName">Organization Name *</Label>
              <Input
                id="orgName"
                value={newOrgName}
                onChange={(e) => setNewOrgName(e.target.value)}
                placeholder="Acme Corporation"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="orgDescription">Description</Label>
              <Input
                id="orgDescription"
                value={newOrgDescription}
                onChange={(e) => setNewOrgDescription(e.target.value)}
                placeholder="Optional description"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="ownerEmail">Owner Email *</Label>
              <Input
                id="ownerEmail"
                type="email"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder="owner@example.com"
              />
              <p className="text-xs text-muted-foreground">
                The user must already exist in the system
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setActionType(null)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleCreateEnterpriseOrg} disabled={isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create Organization'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Feature Flags Dialog */}
      <Dialog open={actionType === 'feature-flags'} onOpenChange={(open) => !open && setActionType(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Feature Flags</DialogTitle>
            <DialogDescription>
              Manage feature flags for {selectedOrg?.name}
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            {availableFeatureFlags.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                Loading available features...
              </div>
            ) : (
              <div className="space-y-3">
                {availableFeatureFlags.map((flag) => {
                  const isEnabled = enabledFeatureFlags.includes(flag.value);
                  return (
                    <div
                      key={flag.value}
                      className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/30 transition-colors"
                    >
                      <div className="flex items-center gap-3">
                        <Flag className={`h-4 w-4 ${isEnabled ? 'text-brand-lime' : 'text-muted-foreground'}`} />
                        <div>
                          <div className="font-medium text-sm">{flag.name.replace(/_/g, ' ')}</div>
                          <div className="text-xs text-muted-foreground">{flag.value}</div>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant={isEnabled ? 'default' : 'outline'}
                        onClick={() => handleToggleFeatureFlag(flag.value, isEnabled)}
                        className="h-7 px-3"
                      >
                        {isEnabled ? 'Enabled' : 'Disabled'}
                      </Button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button onClick={() => setActionType(null)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
