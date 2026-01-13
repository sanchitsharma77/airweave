import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  Eye,
  EyeOff,
  Filter,
  Loader2,
  Plus,
  Search,
  Webhook,
} from "lucide-react";
import {
  useEventsStore,
  type EventMessage,
  type Subscription,
  type MessageAttempt,
  type CreateSubscriptionRequest,
} from "@/lib/stores/events";
import { cn } from "@/lib/utils";

/**
 * Event types configuration - grouped by category
 */
const EVENT_TYPES_CONFIG = {
  sync: {
    label: "Sync Events",
    events: [
      { id: "sync.created", label: "Created" },
      { id: "sync.pending", label: "Pending" },
      { id: "sync.running", label: "Running" },
      { id: "sync.completed", label: "Completed" },
      { id: "sync.failed", label: "Failed" },
      { id: "sync.cancelling", label: "Cancelling" },
      { id: "sync.cancelled", label: "Cancelled" },
      { id: "sync.invalid", label: "Invalid" },
    ],
  },
} as const;

type EventTypeGroup = keyof typeof EVENT_TYPES_CONFIG;

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatFullTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

/**
 * Event Type Selector Component
 */
function EventTypeSelector({
  selectedEventTypes,
  onSelectionChange,
}: {
  selectedEventTypes: string[];
  onSelectionChange: (eventTypes: string[]) => void;
}) {
  const [expandedGroups, setExpandedGroups] = useState<Set<EventTypeGroup>>(
    new Set(Object.keys(EVENT_TYPES_CONFIG) as EventTypeGroup[])
  );

  const toggleGroup = (group: EventTypeGroup) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) {
        next.delete(group);
      } else {
        next.add(group);
      }
      return next;
    });
  };

  const getGroupEventIds = (group: EventTypeGroup): string[] => {
    return EVENT_TYPES_CONFIG[group].events.map((e) => e.id);
  };

  const isGroupFullySelected = (group: EventTypeGroup): boolean => {
    const groupEvents = getGroupEventIds(group);
    return groupEvents.every((id) => selectedEventTypes.includes(id));
  };

  const isGroupPartiallySelected = (group: EventTypeGroup): boolean => {
    const groupEvents = getGroupEventIds(group);
    const selectedCount = groupEvents.filter((id) =>
      selectedEventTypes.includes(id)
    ).length;
    return selectedCount > 0 && selectedCount < groupEvents.length;
  };

  const toggleGroupSelection = (group: EventTypeGroup) => {
    const groupEvents = getGroupEventIds(group);
    if (isGroupFullySelected(group)) {
      onSelectionChange(
        selectedEventTypes.filter((id) => !groupEvents.includes(id))
      );
    } else {
      const newSelection = new Set([...selectedEventTypes, ...groupEvents]);
      onSelectionChange(Array.from(newSelection));
    }
  };

  const toggleEventSelection = (eventId: string) => {
    if (selectedEventTypes.includes(eventId)) {
      onSelectionChange(selectedEventTypes.filter((id) => id !== eventId));
    } else {
      onSelectionChange([...selectedEventTypes, eventId]);
    }
  };

  return (
    <div className="max-h-[250px] overflow-auto border rounded-xl p-3 bg-muted/30">
      {(Object.keys(EVENT_TYPES_CONFIG) as EventTypeGroup[]).map((group) => {
        const config = EVENT_TYPES_CONFIG[group];
        const isExpanded = expandedGroups.has(group);
        const isFullySelected = isGroupFullySelected(group);
        const isPartiallySelected = isGroupPartiallySelected(group);

        return (
          <div key={group}>
            <div
              className="flex cursor-pointer items-center gap-2 py-2 px-2 hover:bg-muted/50 rounded-lg transition-colors"
              onClick={() => toggleGroup(group)}
            >
              <ChevronDown
                className={cn(
                  "text-muted-foreground size-4 transition-transform",
                  !isExpanded && "-rotate-90"
                )}
              />
              <Checkbox
                checked={isFullySelected}
                // @ts-expect-error - indeterminate is a valid prop
                indeterminate={isPartiallySelected}
                onClick={(e) => {
                  e.stopPropagation();
                  toggleGroupSelection(group);
                }}
              />
              <span className="text-sm font-medium">{config.label}</span>
            </div>
            {isExpanded && (
              <div className="ml-6 space-y-0.5">
                {config.events.map((event) => (
                  <label
                    key={event.id}
                    className="flex cursor-pointer items-center gap-2 py-1.5 pl-4 hover:bg-muted/50 rounded-lg transition-colors"
                  >
                    <Checkbox
                      checked={selectedEventTypes.includes(event.id)}
                      onCheckedChange={() => toggleEventSelection(event.id)}
                    />
                    <span className="text-muted-foreground text-sm">
                      {event.label}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Secret validation helpers
 */
const MIN_SECRET_LENGTH = 24;
const MAX_SECRET_LENGTH = 75;

function validateWebhookSecret(secret: string): string | null {
  if (!secret) return null;
  if (secret.length < MIN_SECRET_LENGTH) {
    return `Secret is too short. Must be at least ${MIN_SECRET_LENGTH} characters.`;
  }
  if (secret.length > MAX_SECRET_LENGTH) {
    return `Secret is too long. Must be at most ${MAX_SECRET_LENGTH} characters.`;
  }
  return null;
}

function formatSecretForApi(secret: string): string {
  const base64Encoded = btoa(secret);
  return `whsec_${base64Encoded}`;
}

/**
 * Create Webhook Modal
 */
function CreateWebhookModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { createSubscription } = useEventsStore();
  const [url, setUrl] = useState("");
  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>([]);
  const [secret, setSecret] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const secretValidationError = validateWebhookSecret(secret);
  const isValid = url && selectedEventTypes.length > 0 && !secretValidationError;

  const handleCreate = async () => {
    setIsCreating(true);
    setError(null);
    try {
      const request: CreateSubscriptionRequest = {
        url,
        event_types: selectedEventTypes,
        ...(secret ? { secret: formatSecretForApi(secret) } : {}),
      };
      await createSubscription(request);
      onOpenChange(false);
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create webhook");
    } finally {
      setIsCreating(false);
    }
  };

  const resetForm = () => {
    setUrl("");
    setSelectedEventTypes([]);
    setSecret("");
    setError(null);
  };

  const handleOpenChange = (open: boolean) => {
    if (!open) resetForm();
    onOpenChange(open);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Webhook</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="webhook-url">Webhook URL</Label>
            <Input
              id="webhook-url"
              type="url"
              placeholder="https://example.com/webhook"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="rounded-xl"
            />
            <p className="text-muted-foreground text-xs">
              The URL that will receive webhook events via POST requests.
            </p>
          </div>
          <div className="space-y-2">
            <Label>Event Types</Label>
            <EventTypeSelector
              selectedEventTypes={selectedEventTypes}
              onSelectionChange={setSelectedEventTypes}
            />
            <p className="text-muted-foreground text-xs">
              Select at least one event type to receive.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="webhook-secret">
              Signing Secret{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Input
              id="webhook-secret"
              type="text"
              placeholder="Leave empty to auto-generate (recommended)"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              className={cn("rounded-xl", secretValidationError && "border-destructive")}
            />
            {secretValidationError ? (
              <p className="text-destructive text-xs">{secretValidationError}</p>
            ) : (
              <p className="text-muted-foreground text-xs">
                A secret key used to sign webhook payloads. If not provided, one will be auto-generated.
              </p>
            )}
          </div>
          {error && <p className="text-destructive text-sm">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} className="rounded-lg">
            Cancel
          </Button>
          <Button onClick={handleCreate} disabled={!isValid || isCreating} className="rounded-lg">
            {isCreating ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                Creating...
              </>
            ) : (
              "Create"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Secret Field Component (for edit modal)
 */
function SecretField({ subscriptionId }: { subscriptionId: string }) {
  const { fetchSubscriptionSecret } = useEventsStore();
  const [isRevealed, setIsRevealed] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const handleReveal = async () => {
    if (isRevealed) {
      setIsRevealed(false);
      return;
    }
    if (secret) {
      setIsRevealed(true);
      return;
    }
    setIsLoading(true);
    try {
      const result = await fetchSubscriptionSecret(subscriptionId);
      setSecret(result.key);
      setIsRevealed(true);
    } catch (error) {
      console.error("Failed to fetch secret:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!secret) return;
    try {
      await navigator.clipboard.writeText(secret);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy secret:", error);
    }
  };

  return (
    <div className="space-y-2">
      <Label>Signing Secret</Label>
      <div className="flex items-center gap-2 overflow-hidden">
        <div className="bg-muted/50 w-0 flex-1 overflow-hidden rounded-xl border px-3 py-2">
          <span className="block truncate font-mono text-sm">
            {isRevealed && secret ? secret : "••••••••••••••••••••••••••••••••"}
          </span>
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="shrink-0 rounded-lg"
          onClick={handleCopy}
          disabled={!secret}
          title="Copy to clipboard"
        >
          {isCopied ? <Check className="size-4 text-green-500" /> : <Copy className="size-4" />}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="shrink-0 rounded-lg"
          onClick={handleReveal}
          disabled={isLoading}
          title={isRevealed ? "Hide secret" : "Reveal secret"}
        >
          {isLoading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : isRevealed ? (
            <EyeOff className="size-4" />
          ) : (
            <Eye className="size-4" />
          )}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">
        Use this secret to verify webhook signatures.
      </p>
    </div>
  );
}

/**
 * Message Attempts Table
 */
function MessageAttemptsTable({ attempts }: { attempts: MessageAttempt[] }) {
  if (attempts.length === 0) {
    return <p className="text-muted-foreground text-sm">No delivery attempts yet.</p>;
  }

  const getStatusBadge = (statusCode: number) => {
    if (statusCode >= 200 && statusCode < 300) {
      return <Badge variant="outline" className="bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800">{statusCode}</Badge>;
    } else if (statusCode >= 400 && statusCode < 500) {
      return <Badge variant="outline" className="bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800">{statusCode}</Badge>;
    }
    return <Badge variant="outline" className="bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800">{statusCode}</Badge>;
  };

  return (
    <div className="max-h-[200px] overflow-auto rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Status</TableHead>
            <TableHead>Message ID</TableHead>
            <TableHead className="text-right">Timestamp</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {attempts.map((attempt) => (
            <TableRow key={attempt.id}>
              <TableCell>{getStatusBadge(attempt.responseStatusCode)}</TableCell>
              <TableCell className="max-w-[150px] truncate font-mono text-xs">
                {attempt.msgId}
              </TableCell>
              <TableCell className="text-muted-foreground text-right text-sm">
                {formatTimestamp(attempt.timestamp)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * Edit Subscription Modal
 */
function EditSubscriptionModal({
  subscriptionId,
  open,
  onOpenChange,
}: {
  subscriptionId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { fetchSubscription, updateSubscription, deleteSubscription } = useEventsStore();
  const [url, setUrl] = useState("");
  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>([]);
  const [messageAttempts, setMessageAttempts] = useState<MessageAttempt[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (open && subscriptionId) {
      setIsLoading(true);
      fetchSubscription(subscriptionId)
        .then((data) => {
          setUrl(data.endpoint.url);
          setSelectedEventTypes(data.endpoint.channels || []);
          setMessageAttempts(data.message_attempts || []);
        })
        .finally(() => setIsLoading(false));
    }
  }, [open, subscriptionId, fetchSubscription]);

  const handleUpdate = async () => {
    if (!subscriptionId) return;
    setIsUpdating(true);
    try {
      await updateSubscription(subscriptionId, { url, event_types: selectedEventTypes });
      onOpenChange(false);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = async () => {
    if (!subscriptionId) return;
    setIsDeleting(true);
    try {
      await deleteSubscription(subscriptionId);
      onOpenChange(false);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!subscriptionId) return null;

  const isValid = url && selectedEventTypes.length > 0;
  const isPending = isUpdating || isDeleting;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit Webhook</DialogTitle>
        </DialogHeader>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="text-muted-foreground size-6 animate-spin" />
          </div>
        ) : (
          <>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-webhook-url">Webhook URL</Label>
                <Input
                  id="edit-webhook-url"
                  type="url"
                  placeholder="https://example.com/webhook"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  className="rounded-xl"
                />
              </div>
              <div className="space-y-2">
                <Label>Event Types</Label>
                <EventTypeSelector
                  selectedEventTypes={selectedEventTypes}
                  onSelectionChange={setSelectedEventTypes}
                />
              </div>
              <SecretField subscriptionId={subscriptionId} />
              <div className="space-y-2">
                <Label>Delivery Attempts</Label>
                <MessageAttemptsTable attempts={messageAttempts} />
              </div>
            </div>
            <DialogFooter className="flex-row justify-between sm:justify-between">
              <Button variant="destructive" onClick={handleDelete} disabled={isPending} className="rounded-lg">
                {isDeleting ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  "Delete"
                )}
              </Button>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">
                  Cancel
                </Button>
                <Button onClick={handleUpdate} disabled={!isValid || isPending} className="rounded-lg">
                  {isUpdating ? (
                    <>
                      <Loader2 className="mr-2 size-4 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    "Update"
                  )}
                </Button>
              </div>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Event Detail Modal
 */
function EventDetailModal({
  event,
  open,
  onOpenChange,
}: {
  event: EventMessage | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!event) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="font-mono">{event.eventType}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-3 text-sm">
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Event ID</p>
              <p className="font-mono break-all">{event.id}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs uppercase tracking-wider mb-1">Timestamp</p>
              <p>{formatFullTimestamp(event.timestamp)}</p>
            </div>
          </div>
          {event.channels && event.channels.length > 0 && (
            <div>
              <p className="text-muted-foreground mb-1 text-xs uppercase tracking-wider">Channels</p>
              <p className="text-sm">{event.channels.join(", ")}</p>
            </div>
          )}
          <div>
            <p className="text-muted-foreground mb-2 text-xs uppercase tracking-wider">Payload</p>
            <pre className="bg-muted/50 max-h-[300px] overflow-auto rounded-xl p-4 text-xs border">
              <code>{JSON.stringify(event.payload, null, 2)}</code>
            </pre>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Messages Filter Modal
 */
function MessagesFilterModal({
  open,
  onOpenChange,
  selectedEventTypes,
  onApply,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedEventTypes: string[];
  onApply: (eventTypes: string[]) => void;
}) {
  const [localSelectedEventTypes, setLocalSelectedEventTypes] = useState<string[]>(selectedEventTypes);

  useEffect(() => {
    if (open) {
      setLocalSelectedEventTypes(selectedEventTypes);
    }
  }, [open, selectedEventTypes]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Filter Event Messages</DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <EventTypeSelector
            selectedEventTypes={localSelectedEventTypes}
            onSelectionChange={setLocalSelectedEventTypes}
          />
          <p className="text-muted-foreground mt-2 text-xs">
            Select event types to filter. Leave empty to show all events.
          </p>
        </div>
        <DialogFooter className="flex-row justify-between sm:justify-between">
          <Button variant="outline" onClick={() => setLocalSelectedEventTypes([])} className="rounded-lg">
            Clear
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-lg">
              Cancel
            </Button>
            <Button onClick={() => { onApply(localSelectedEventTypes); onOpenChange(false); }} className="rounded-lg">
              Apply
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Empty State Component
 */
function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24">
      <div className="rounded-full bg-gradient-to-br from-primary/10 to-primary/5 p-6 mb-6">
        <Webhook className="size-10 text-primary" />
      </div>
      <h3 className="text-xl font-semibold mb-2">Add your first webhook</h3>
      <p className="text-muted-foreground text-center mb-8 max-w-md">
        Get notified when sync jobs complete, fail, or when new data is available.
      </p>
      <Button onClick={onCreateClick} className="rounded-lg h-10 px-5">
        <Plus className="mr-2 size-4" />
        Create Webhook
      </Button>
    </div>
  );
}

/**
 * Webhook Card Component
 */
function WebhookCard({
  subscription,
  onClick,
}: {
  subscription: Subscription;
  onClick: () => void;
}) {
  const channelCount = subscription.channels?.length || 0;

  return (
    <div
      onClick={onClick}
      className="group relative bg-card border rounded-xl p-5 hover:border-primary/30 hover:shadow-md transition-all duration-200 cursor-pointer"
    >
      <div className="flex items-start gap-4">
        <div className="shrink-0 p-2.5 rounded-lg bg-primary/10">
          <Webhook className="size-5 text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-mono text-sm truncate mb-1.5" title={subscription.url}>
            {subscription.url}
          </p>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{channelCount} event{channelCount !== 1 ? "s" : ""}</span>
            <span>•</span>
            <span>{formatTimestamp(subscription.createdAt)}</span>
          </div>
        </div>
      </div>
      {/* Hover indicator */}
      <div className="absolute inset-0 rounded-xl ring-1 ring-inset ring-transparent group-hover:ring-primary/20 transition-all pointer-events-none" />
    </div>
  );
}

/**
 * Main Webhooks Page
 */
const WebhooksPage = () => {
  const {
    subscriptions,
    messages,
    isLoadingSubscriptions,
    isLoadingMessages,
    error,
    fetchSubscriptions,
    fetchMessages,
  } = useEventsStore();

  const [selectedEvent, setSelectedEvent] = useState<EventMessage | null>(null);
  const [eventModalOpen, setEventModalOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [selectedSubscriptionId, setSelectedSubscriptionId] = useState<string | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [filterEventTypes, setFilterEventTypes] = useState<string[]>([]);
  const [filterModalOpen, setFilterModalOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination for messages
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Fetch data on mount
  useEffect(() => {
    fetchSubscriptions();
    fetchMessages();
  }, [fetchSubscriptions, fetchMessages]);

  // Refetch messages when filter changes
  useEffect(() => {
    fetchMessages(filterEventTypes.length > 0 ? filterEventTypes : undefined);
  }, [filterEventTypes, fetchMessages]);

  // Filter messages by search
  const filteredMessages = messages.filter((msg) =>
    !searchQuery || msg.eventType.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Paginate messages
  const totalPages = Math.ceil(filteredMessages.length / itemsPerPage);
  const paginatedMessages = filteredMessages.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reset page when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  const handleEventClick = (event: EventMessage) => {
    setSelectedEvent(event);
    setEventModalOpen(true);
  };

  const handleSubscriptionClick = (subscription: Subscription) => {
    setSelectedSubscriptionId(subscription.id);
    setEditModalOpen(true);
  };

  const handleFilterApply = (eventTypes: string[]) => {
    setFilterEventTypes(eventTypes);
  };

  const hasFilter = filterEventTypes.length > 0;

  // Loading state
  if (isLoadingSubscriptions) {
    return (
      <div className="mx-auto w-full max-w-[1800px] px-6 py-6 pb-8">
        {/* Header skeleton */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8 gap-4">
          <div>
            <div className="h-9 w-40 bg-muted rounded-lg animate-pulse mb-2" />
            <div className="h-4 w-64 bg-muted rounded animate-pulse" />
          </div>
          <div className="h-9 w-36 bg-muted rounded-lg animate-pulse" />
        </div>
        {/* Grid skeleton */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-[1800px] px-6 py-6 pb-8">
        <div className="flex flex-col items-center justify-center py-24">
          <p className="text-destructive text-sm">Failed to load data: {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[1800px] px-6 py-6 pb-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8 gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-3xl font-bold">Webhooks</h1>
            {subscriptions.length > 0 && (
              <span className="px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground rounded-full">
                {subscriptions.length}
              </span>
            )}
            <Badge variant="secondary" className="bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 border-0">
              Beta
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Receive real-time event notifications via HTTP POST
          </p>
        </div>
        <Button
          onClick={() => setCreateModalOpen(true)}
          className="bg-primary text-white rounded-lg h-9 px-4 hover:bg-primary/90 transition-all duration-200"
        >
          <Plus className="mr-2 h-4 w-4" />
          Create Webhook
        </Button>
      </div>

      {subscriptions.length === 0 && messages.length === 0 ? (
        <EmptyState onCreateClick={() => setCreateModalOpen(true)} />
      ) : (
        <div className="space-y-10">
          {/* Subscriptions Section */}
          <section>
            <div className="flex items-center gap-3 mb-4">
              <h2 className="text-lg font-semibold">Subscriptions</h2>
              <span className="px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground rounded-full">
                {subscriptions.length}
              </span>
            </div>
            {subscriptions.length === 0 ? (
              <div className="text-muted-foreground text-sm py-8 text-center border rounded-xl bg-muted/20">
                No subscriptions configured yet.
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {subscriptions.map((subscription) => (
                  <WebhookCard
                    key={subscription.id}
                    subscription={subscription}
                    onClick={() => handleSubscriptionClick(subscription)}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Event Messages Section */}
          <section>
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-semibold">Event Messages</h2>
                {messages.length > 0 && (
                  <span className="px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground rounded-full">
                    {filteredMessages.length}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <div className="relative flex-1 sm:flex-initial sm:w-64">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    type="text"
                    placeholder="Search events..."
                    className="pl-10 h-9 rounded-xl border-border focus:border-text/50 focus:ring-0"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                <Button
                  size="sm"
                  variant={hasFilter ? "default" : "outline"}
                  onClick={() => setFilterModalOpen(true)}
                  className="rounded-lg h-9"
                >
                  <Filter className="mr-2 size-4" />
                  Filter{hasFilter && ` (${filterEventTypes.length})`}
                </Button>
              </div>
            </div>

            {isLoadingMessages ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="text-muted-foreground size-6 animate-spin" />
              </div>
            ) : paginatedMessages.length === 0 ? (
              <div className="py-16 text-center border rounded-xl bg-muted/20">
                <p className="text-muted-foreground text-sm">
                  {hasFilter || searchQuery ? "No messages match the filter." : "No messages yet."}
                </p>
              </div>
            ) : (
              <>
                <div className="border rounded-xl overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/30 hover:bg-muted/30">
                        <TableHead className="font-medium">Event Type</TableHead>
                        <TableHead className="text-right font-medium">Timestamp</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedMessages.map((message) => (
                        <TableRow
                          key={message.id}
                          className="cursor-pointer hover:bg-muted/50 transition-colors"
                          onClick={() => handleEventClick(message)}
                        >
                          <TableCell className="font-mono text-sm">
                            <span className="inline-flex items-center gap-2">
                              <span className="size-2 rounded-full bg-primary/60" />
                              {message.eventType}
                            </span>
                          </TableCell>
                          <TableCell className="text-muted-foreground text-right text-sm">
                            {formatTimestamp(message.timestamp)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="mt-6 flex items-center justify-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                      className={cn(
                        "gap-1 hover:bg-accent rounded-lg",
                        currentPage === 1 && "opacity-40 cursor-not-allowed"
                      )}
                    >
                      <ChevronLeft className="h-4 w-4" />
                      Previous
                    </Button>

                    <div className="flex items-center gap-1.5">
                      {[...Array(totalPages)].map((_, i) => {
                        const page = i + 1;
                        if (
                          page === 1 ||
                          page === totalPages ||
                          (page >= currentPage - 1 && page <= currentPage + 1)
                        ) {
                          return (
                            <Button
                              key={page}
                              variant="ghost"
                              size="sm"
                              onClick={() => setCurrentPage(page)}
                              className={cn(
                                "min-w-[40px] hover:bg-accent transition-colors rounded-lg",
                                currentPage === page
                                  ? "bg-muted font-medium text-foreground shadow-sm"
                                  : "text-muted-foreground hover:text-foreground"
                              )}
                            >
                              {page}
                            </Button>
                          );
                        } else if (page === currentPage - 2 || page === currentPage + 2) {
                          return (
                            <span key={page} className="px-2 text-muted-foreground">
                              ...
                            </span>
                          );
                        }
                        return null;
                      })}
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage === totalPages}
                      className={cn(
                        "gap-1 hover:bg-accent rounded-lg",
                        currentPage === totalPages && "opacity-40 cursor-not-allowed"
                      )}
                    >
                      Next
                      <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}

      {/* Modals */}
      <EventDetailModal
        event={selectedEvent}
        open={eventModalOpen}
        onOpenChange={setEventModalOpen}
      />
      <CreateWebhookModal
        open={createModalOpen}
        onOpenChange={setCreateModalOpen}
      />
      <EditSubscriptionModal
        subscriptionId={selectedSubscriptionId}
        open={editModalOpen}
        onOpenChange={setEditModalOpen}
      />
      <MessagesFilterModal
        open={filterModalOpen}
        onOpenChange={setFilterModalOpen}
        selectedEventTypes={filterEventTypes}
        onApply={handleFilterApply}
      />
    </div>
  );
};

export default WebhooksPage;
