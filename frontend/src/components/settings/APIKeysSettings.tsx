import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Key, Copy, Loader2, AlertCircle, Clock, CalendarIcon, CheckCircle, Trash2, Shield } from "lucide-react";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { format, differenceInDays } from "date-fns";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme-provider";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useAPIKeysStore, type APIKey } from "@/lib/stores/apiKeys";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function APIKeysSettings() {
  // Use the store instead of local state
  const {
    apiKeys,
    isLoading: loading,
    error,
    fetchAPIKeys,
    createAPIKey,
    deleteAPIKey
  } = useAPIKeysStore();

  const [newlyCreatedKey, setNewlyCreatedKey] = useState<APIKey | null>(null);
  const [copySuccess, setCopySuccess] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [keyToDelete, setKeyToDelete] = useState<APIKey | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    fetchAPIKeys();
  }, [fetchAPIKeys]);

  const maskApiKey = (key: string) => {
    if (!key) return "";
    const firstFour = key.substring(0, 4);
    const masked = Array(key.length - 4).fill("*").join("");
    return `${firstFour}${masked}`;
  };

  const handleCreateApiKey = async () => {
    setCreating(true);

    try {
      const newKey = await createAPIKey();
      setNewlyCreatedKey(newKey);
      toast.success("API key created successfully");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to create API key. Please try again.";
      toast.error(errorMessage);
    } finally {
      setCreating(false);
    }
  };

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key).then(
      () => {
        setCopySuccess(key);
        toast.success("API key copied to clipboard");
        setTimeout(() => setCopySuccess(null), 2000);
      },
      () => {
        toast.error("Failed to copy API key");
      }
    );
  };

  const openDeleteDialog = (apiKey: APIKey) => {
    setKeyToDelete(apiKey);
    setDeleteDialogOpen(true);
  };

  const handleDeleteKey = async (id: string) => {
    setDeleting(true);
    try {
      await deleteAPIKey(id);
      toast.success("API key deleted successfully");

      // If we just deleted the newly created key, clear that state
      if (newlyCreatedKey && newlyCreatedKey.id === id) {
        setNewlyCreatedKey(null);
      }

      setDeleteDialogOpen(false);
      setKeyToDelete(null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to delete API key. Please try again.";
      toast.error(errorMessage);
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (dateString: string, includeRelative: boolean = false) => {
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return "Invalid date";

      const formattedDate = format(date, "PPP");

      if (includeRelative) {
        const now = new Date();
        const daysRemaining = differenceInDays(date, now);

        if (daysRemaining < 0) {
          return `${formattedDate} (Expired)`;
        } else if (daysRemaining === 0) {
          return `${formattedDate} (Today)`;
        } else if (daysRemaining === 1) {
          return `${formattedDate} (Tomorrow)`;
        } else {
          return `${formattedDate} (${daysRemaining} days remaining)`;
        }
      }

      return formattedDate;
    } catch (e) {
      console.error("Error formatting date:", e);
      return "Invalid date";
    }
  };

  const getExpirationStatus = (expirationDate: string) => {
    try {
      const date = new Date(expirationDate);
      const now = new Date();
      const daysRemaining = differenceInDays(date, now);

      if (daysRemaining < 0) {
        return "EXPIRED";
      } else if (daysRemaining <= 7) {
        return "EXPIRING_SOON";
      } else {
        return "ACTIVE";
      }
    } catch (e) {
      return "UNKNOWN";
    }
  };

  return (
    <div className="space-y-4">

      <div className="py-2 space-y-8">
        {/* Create new API key section */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <h3 className="text-sm font-medium">Create new API key</h3>
            <p className="text-xs text-muted-foreground">
              API keys will expire 180 days after creation
            </p>
          </div>
          <Button
            onClick={handleCreateApiKey}
            disabled={creating}
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-white h-8 px-3.5 text-sm w-full sm:w-auto"
          >
            {creating ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Key className="h-3 w-3" />
            )}
            {creating ? 'Creating...' : 'Create key'}
          </Button>
        </div>

        {/* Newly created key alert */}
        {newlyCreatedKey && newlyCreatedKey.decrypted_key && (
          <div className={cn(
            "py-4 space-y-4",
            isDark ? "border-t border-b border-slate-800" : "border-t border-b border-slate-200"
          )}>
            <div className="space-y-2">
              <h4 className="font-medium">Your new API key has been created</h4>
            </div>

            <div className="flex items-stretch gap-2">
              <div className="flex-grow relative">
                <Input
                  type="text"
                  value={newlyCreatedKey.decrypted_key}
                  readOnly
                  className="font-mono text-sm h-9 pr-10"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleCopyKey(newlyCreatedKey.decrypted_key || "")}
                  className="absolute right-0 top-0 h-full rounded-l-none"
                >
                  {copySuccess === newlyCreatedKey.decrypted_key ? (
                    <CheckCircle className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>

            <Button
              variant="link"
              size="sm"
              onClick={() => setNewlyCreatedKey(null)}
              className="px-0 h-auto"
            >
              I've saved the key
            </Button>
          </div>
        )}

        {/* Error state */}
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Loading state */}
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            {/* API Keys list */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Your API keys</h3>
                <div className="text-xs text-muted-foreground">{apiKeys.length} key{apiKeys.length !== 1 ? 's' : ''}</div>
              </div>

              {apiKeys.length === 0 ? (
                <div className={cn(
                  "rounded-lg border border-dashed p-8 text-center",
                  isDark ? "border-slate-800" : "border-slate-200"
                )}>
                  <Key className="mx-auto h-8 w-8 text-muted-foreground opacity-50" />
                  <h3 className="mt-2 text-sm font-medium">No API keys</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    You don't have any API keys yet. Create one to get started.
                  </p>
                </div>
              ) : (
                <div className="grid gap-3">
                  {apiKeys.map((apiKey) => {
                    const status = getExpirationStatus(apiKey.expiration_date);
                    const date = new Date(apiKey.expiration_date);
                    const now = new Date();
                    const daysRemaining = differenceInDays(date, now);
                    const isExpiringSoon = daysRemaining >= 0 && daysRemaining <= 7;
                    const isExpired = daysRemaining < 0;

                    return (
                      <div
                        key={apiKey.id}
                        className={cn(
                          "relative rounded-xl overflow-hidden cursor-default",
                          "border",
                          isDark
                            ? "border-slate-800 hover:border-slate-700"
                            : "border-slate-200 hover:border-slate-300",
                          "transition-all duration-200"
                        )}
                      >
                        <div className="p-4">
                          <div className="space-y-3">
                            {/* Key and controls */}
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Key className={cn("h-4 w-4", isDark ? "text-blue-400" : "text-blue-500")} />
                                <code className="font-mono text-sm font-medium">
                                  {maskApiKey(apiKey.decrypted_key)}
                                </code>
                              </div>
                              <div className="flex items-center gap-2">
                                <StatusBadge status={status} showTooltip={true} tooltipContext="apiKey" />
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-7 w-7 rounded-full hover:bg-transparent"
                                  onClick={() => handleCopyKey(apiKey.decrypted_key)}
                                >
                                  {copySuccess === apiKey.decrypted_key ? (
                                    <CheckCircle className="h-3.5 w-3.5" />
                                  ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className={cn(
                                    "h-7 w-7 rounded-full hover:bg-transparent",
                                    isDark ? "hover:text-red-300" : "hover:text-red-600"
                                  )}
                                  onClick={() => openDeleteDialog(apiKey)}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </div>
                            </div>

                            {/* Divider */}
                            <div className={cn(
                              "h-px w-full",
                              isDark ? "bg-slate-800" : "bg-slate-100"
                            )} />

                            {/* Dates */}
                            <div className="flex justify-between items-center text-xs text-muted-foreground">
                              <div className="flex items-center gap-1.5">
                                <CalendarIcon className="h-3 w-3" />
                                <span>Created {formatDate(apiKey.created_at)}</span>
                              </div>
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3 w-3" />
                                <span className={cn(
                                  isExpired
                                    ? isDark ? "text-red-400" : "text-red-500"
                                    : isExpiringSoon
                                      ? isDark ? "text-amber-400" : "text-amber-500"
                                      : "text-muted-foreground"
                                )}>
                                  Expires: {formatDate(apiKey.expiration_date, true)}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className={cn("h-5 w-5", isDark ? "text-amber-400" : "text-amber-500")} />
              Confirm API Key Deletion
            </DialogTitle>
            <DialogDescription>
              This action cannot be undone. The API key will be permanently deleted and any applications using it will no longer be able to authenticate.
            </DialogDescription>
          </DialogHeader>

          {keyToDelete && (
            <div className={cn(
              "my-4 p-3 rounded-md",
              isDark ? "bg-slate-900 border border-slate-800" : "bg-slate-50 border border-slate-200"
            )}>
              <div className="flex items-center gap-2 font-mono text-sm">
                <Key className={cn("h-4 w-4", isDark ? "text-blue-400" : "text-blue-500")} />
                {maskApiKey(keyToDelete.decrypted_key)}
              </div>
            </div>
          )}

          <DialogFooter className="sm:justify-between gap-3 mt-2">
            <Button
              variant="ghost"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => keyToDelete && handleDeleteKey(keyToDelete.id)}
              disabled={deleting}
              className="sm:w-auto w-full"
            >
              {deleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="mr-2 h-4 w-4" />
                  Delete API Key
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
