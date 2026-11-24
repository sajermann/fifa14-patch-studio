import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Footprints,
  Hand,
  LoaderCircle,
  Upload,
  Volleyball,
} from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { api } from "@/api/client";
import type { Equipment, EquipmentKind } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useI18n, type MessageKey } from "@/i18n";
import { cn } from "@/lib/utils";
import { useToken } from "@/state/queries";

/** What changes between boots, gloves and balls on the screens (the Street Studio's three pages: BootsPage,
 * GlovesPage, BallsPage and their edit pages). `t` = the prefix of their texts. */
export const KINDS: Record<
  EquipmentKind,
  {
    t: "boots" | "gloves" | "balls";
    path: string;
    icon: typeof Footprints;
    thumb: string;
  }
> = {
  boot: { t: "boots", path: "/boots", icon: Footprints, thumb: "h-7 w-14" },
  glove: { t: "gloves", path: "/gloves", icon: Hand, thumb: "size-8" },
  ball: { t: "balls", path: "/balls", icon: Volleyball, thumb: "size-8" },
};

/** A text of the kind's own set (boots.*, gloves.*, balls.*). */
export function useKindText(kind: EquipmentKind) {
  const { t } = useI18n();
  const prefix = KINDS[kind].t;
  return (key: string, vars?: Record<string, string | number>) =>
    t(`${prefix}.${key}` as MessageKey, vars);
}

export const equipmentPath = (kind: EquipmentKind, code: number) =>
  `${KINDS[kind].path}/${code}`;

/** The shown name: the user's, else the game's own name, else the game's item by its code (as the Street Studio:
 * "Original <code>"). */
export function useEquipmentName() {
  const { t } = useI18n();
  return (item: Pick<Equipment, "name" | "code" | "is_new" | "game_name">) =>
    item.name.trim() ||
    (item.is_new
      ? t("common.unnamed")
      : item.game_name || `Original ${item.code}`);
}

export function useEquipmentList(kind: EquipmentKind) {
  const token = useToken();
  return useQuery({
    queryKey: ["equipment", kind, token],
    queryFn: () => api.equipmentList(kind),
    enabled: !!token,
  });
}

/** The warnings of an item (files missing, a new glove the game's editor does not list). */
export function useEquipmentWarnings() {
  const { t } = useI18n();
  return (item: Pick<Equipment, "is_new" | "complete" | "listed">) => [
    ...(item.is_new && !item.complete
      ? [t("equipment.missingFilesWarning")]
      : []),
    ...(!item.listed ? [t("gloves.notListedHint")] : []),
  ];
}

/** The warning mark of the other screens (EntityIssues): the icon and how many, the texts in a tooltip. */
export function EquipmentWarnings({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help items-center gap-1 text-xs text-amber-600 dark:text-amber-500">
          <AlertTriangle className="size-3" /> {warnings.length}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm">
        <ul className="list-disc space-y-1 pl-4">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}

/** Revision of how the server reads an item's model (drawn pictures and the 3D preview): raised when that changes,
 * so the browser does not keep the old ones (cached for a year per item version). */
export const MODEL_REVISION = 2;

export const equipmentPictureUrl = (
  kind: EquipmentKind,
  code: number,
  version: number | null | undefined,
) =>
  `/api/equipment/${kind}/${code}/picture.png?v=${version ?? 0}&r=${MODEL_REVISION}`;

/** List picture of a boot, glove or ball: the user's picture, else drawn from its files (the project's or the
 * game's) by the backend (the Street Studio's BootThumb / GloveThumb / BallThumb). */
export function EquipmentThumb({
  kind,
  item,
  code,
  className,
}: {
  kind: EquipmentKind;
  item?: Pick<Equipment, "code" | "picture" | "version">;
  code?: number;
  className?: string;
}) {
  const Icon = KINDS[kind].icon;
  const c = item?.code ?? code;
  const src =
    c != null
      ? equipmentPictureUrl(kind, c, item ? (item.picture ?? item.version) : 0)
      : undefined;
  const [failed, setFailed] = useState<string>();
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded bg-muted",
        KINDS[kind].thumb,
        className,
      )}
    >
      {src && failed !== src ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          className="size-full object-contain"
          onError={() => setFailed(src)}
        />
      ) : (
        <Icon className="size-4 text-muted-foreground/60" />
      )}
    </span>
  );
}

/** One file of the item (the Street Studio's FileField): sent or not, with its Send/Replace button. */
export function FileField({
  label,
  hint,
  has,
  pending,
  fallback,
  onPick,
  extra,
}: {
  label: string;
  hint: string;
  has: boolean;
  pending?: boolean;
  fallback?: string;
  onPick: (file: File) => Promise<void>;
  extra?: ReactNode;
}) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={
            has || pending ? "text-sm" : "text-sm text-muted-foreground"
          }
        >
          {pending
            ? t("equipment.filePending")
            : has
              ? t("boots.fileSent")
              : (fallback ?? t("boots.fileMissing"))}
        </span>
        <input
          ref={input}
          type="file"
          accept=".rx3"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            setBusy(true);
            onPick(file).finally(() => setBusy(false));
          }}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {busy ? <LoaderCircle className="animate-spin" /> : <Upload />}{" "}
          {has || pending ? t("boots.fileReplace") : t("boots.fileSend")}
        </Button>
        {extra}
      </div>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
