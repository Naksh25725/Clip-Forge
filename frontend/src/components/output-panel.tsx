"use client";

import {
  Check,
  CloudUpload,
  ExternalLink,
  FolderOpen,
  Loader2,
  RefreshCw,
  Unplug,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import * as services from "@/services";
import type { DriveFolder, DriveStatus, SplitOptions } from "@/types";

export function OutputPanel({
  options,
  onChange,
  driveStatus,
  onDriveChanged,
  disabled,
}: {
  options: SplitOptions;
  onChange: (next: SplitOptions) => void;
  driveStatus?: DriveStatus;
  onDriveChanged: () => void;
  disabled?: boolean;
}) {
  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [checking, setChecking] = useState(false);
  const [folderOk, setFolderOk] = useState<boolean | null>(null);
  const [loadingFolders, setLoadingFolders] = useState(false);

  const set = <K extends keyof SplitOptions>(key: K, value: SplitOptions[K]) =>
    onChange({ ...options, [key]: value });

  const loadFolders = async () => {
    setLoadingFolders(true);
    try {
      setFolders(await services.drive.folders());
    } catch {
      setFolders([]);
    } finally {
      setLoadingFolders(false);
    }
  };

  useEffect(() => {
    if (options.output_mode === "drive" && driveStatus?.connected) loadFolders();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.output_mode, driveStatus?.connected]);

  useEffect(() => setFolderOk(null), [options.output_dir]);

  const checkFolder = async () => {
    setChecking(true);
    try {
      const result = await services.settings.checkFolder(options.output_dir);
      setFolderOk(result.ok);
      if (result.ok) {
        toast.success(`Folder ready: ${result.resolved}`);
        onChange({ ...options, output_dir: result.resolved });
      } else {
        toast.error(result.message);
      }
    } catch (e) {
      setFolderOk(false);
      toast.error(errorMessage(e, "Could not check that folder"));
    } finally {
      setChecking(false);
    }
  };

  const connectDrive = async () => {
    try {
      const { url } = await services.drive.authUrl();
      window.location.href = url;
    } catch (e) {
      toast.error(errorMessage(e, "Google Drive isn't configured"));
    }
  };

  const disconnectDrive = async () => {
    await services.drive.disconnect();
    onDriveChanged();
    toast.success("Google Drive disconnected");
  };

  const MODES = [
    { key: "local", label: "Folder on this device", icon: FolderOpen },
    { key: "drive", label: "Google Drive", icon: CloudUpload },
    { key: "none", label: "Keep in app only", icon: Check },
  ] as const;

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-3">
        {MODES.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            disabled={disabled}
            onClick={() => set("output_mode", key)}
            className={cn(
              "flex items-center gap-2 rounded-xl border p-3 text-left text-sm transition-colors disabled:opacity-50",
              options.output_mode === key
                ? "border-primary/50 bg-primary/10"
                : "border-white/[0.08] hover:bg-white/[0.04]",
            )}
          >
            <Icon className="h-4 w-4 shrink-0 text-violet-300" />
            <span className="font-medium">{label}</span>
          </button>
        ))}
      </div>

      {options.output_mode === "local" && (
        <div>
          <Label className="mb-1.5 block text-xs">Folder path</Label>
          <div className="flex gap-2">
            <Input
              value={options.output_dir}
              disabled={disabled}
              onChange={(e) => set("output_dir", e.target.value)}
              placeholder="C:\Users\you\Videos\ClipForge"
              className={cn(
                folderOk === true && "border-emerald-500/50",
                folderOk === false && "border-red-500/50",
              )}
            />
            <Button variant="outline" onClick={checkFolder} disabled={checking || disabled}>
              {checking ? <Loader2 className="animate-spin" /> : <FolderOpen />} Check
            </Button>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Parts are saved here automatically as they finish. The folder is created if it doesn’t
            exist.
          </p>
        </div>
      )}

      {options.output_mode === "drive" && (
        <div>
          {!driveStatus?.configured ? (
            <p className="text-sm text-muted-foreground">
              Drive isn’t configured. Add <code className="text-violet-300">GOOGLE_CLIENT_ID</code>{" "}
              and <code className="text-violet-300">GOOGLE_CLIENT_SECRET</code> to your{" "}
              <code className="text-violet-300">.env</code>, then restart the backend. See the
              README for the 2-minute setup.
            </p>
          ) : !driveStatus.connected ? (
            <Button onClick={connectDrive} disabled={disabled}>
              <ExternalLink /> Connect Google Drive
            </Button>
          ) : (
            <div className="space-y-2">
              <Label className="text-xs">Destination folder</Label>
              <div className="flex gap-2">
                <Select
                  value={options.drive_folder_id}
                  disabled={disabled}
                  onValueChange={(v) => set("drive_folder_id", v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a folder" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="root">My Drive (root)</SelectItem>
                    {folders.map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant="outline" size="icon" onClick={loadFolders} disabled={loadingFolders}>
                  {loadingFolders ? <Loader2 className="animate-spin" /> : <RefreshCw />}
                </Button>
              </div>
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-muted-foreground">
                  Signed in as {driveStatus.account_email || "your Google account"}
                </span>
                <Button variant="ghost" size="sm" onClick={disconnectDrive}>
                  <Unplug /> Disconnect
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {options.output_mode === "none" && (
        <p className="text-sm text-muted-foreground">
          Parts stay in ClipForge — download them individually, or save them somewhere later.
        </p>
      )}
    </div>
  );
}
