import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ImageOff,
  Info,
  Loader2,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api/client";
import type { Equipment, EquipmentKind } from "@/api/types";
import { EntryDates } from "@/components/common/dates";
import { OriginalBadge, Section } from "@/components/common/detail";
import { EditActions, useEntityForm } from "@/components/common/edit";
import {
  HideButton,
  OutOfPatchBadge,
  usePendingHide,
} from "@/components/common/HideButton";
import { readPicture } from "@/components/common/pictures";
import {
  equipmentPictureUrl,
  EquipmentThumb,
  EquipmentWarnings,
  FileField,
  KINDS,
  useEquipmentName,
  useEquipmentWarnings,
  useKindText,
} from "@/components/equipment/equipment";
import { EquipmentPreview } from "@/components/equipment/EquipmentPreview";
import { LoadingBlock } from "@/components/layout/LoadingBlock";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n, type MessageKey } from "@/i18n";
import { BackButton, useBack, useFrom } from "@/lib/back";
import { toast } from "@/lib/notify";
import { useToken } from "@/state/queries";
import { ExportButton } from "@/components/common/ShareExport";

/** Files and picture chosen and not saved yet (base64), or a saved one to drop. */
type Pending = {
  mesh?: string;
  texture?: string;
  remove: string[];
  picture?: { data: string; url: string } | "remove";
};
const NOTHING: Pending = { remove: [] };

/** The note of the game's own edit player screen for this item (boots and the game's gloves are listed there with
 * their name; a new glove is not: changed there, it cannot be picked again). */
export function ListedNote({
  kind,
  item,
}: {
  kind: EquipmentKind;
  item: Pick<Equipment, "listed" | "is_new">;
}) {
  const { t } = useI18n();
  if (kind === "ball") return null;
  if (!item.listed)
    return (
      <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        <span>{t("gloves.notListedWarning")}</span>
      </div>
    );
  return (
    <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
      <Info className="mt-0.5 size-3.5 shrink-0" />
      <span>
        {t(kind === "boot" ? "boots.listedNote" : "gloves.listedNote")}
      </span>
    </p>
  );
}

/** One boot, glove or ball (the Street Studio's BootEditPage / GloveEditPage / BallEditPage): its name and credits,
 * the pack's files, its picture and who wears it. A new item (its own code) or one of the game's (new files change it
 * for everyone using its code; restored by Restore). Saved as the other screens of this app (Save / Discard). */
export function EquipmentEditPage({ kind }: { kind: EquipmentKind }) {
  const { t } = useI18n();
  const k = useKindText(kind);
  const code = Number(useParams().id);
  const token = useToken();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const nameOf = useEquipmentName();
  const warningsOf = useEquipmentWarnings();
  const navKey = `nav.${KINDS[kind].t}` as MessageKey;
  const queryKey = ["equipment-item", kind, token, code];
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => api.equipment(kind, code),
    enabled: !!token,
  });
  const back = useBack({ to: KINDS[kind].path, label: { key: navKey } });
  const from = useFrom(data ? nameOf(data) : { key: navKey });
  const hide = usePendingHide(data?.hidden);
  const [pending, setPending] = useState<Pending>(NOTHING);
  const [deleting, setDeleting] = useState(false);
  const pictureInput = useRef<HTMLInputElement>(null);
  const pendingUrl =
    pending.picture && pending.picture !== "remove"
      ? pending.picture.url
      : null;
  useEffect(
    () => () => void (pendingUrl && URL.revokeObjectURL(pendingUrl)),
    [pendingUrl],
  );
  const clearPending = () => {
    setPending(NOTHING);
    hide.clear();
  };
  const isNew = !!data?.is_new;
  // a game item shows the game's own name and credits (EA) as its values; saved as they are, they stay the game's
  const gameText = (name: "name" | "credits" | "credits_url") =>
    isNew || !data
      ? ""
      : name === "name"
        ? (data.game_name ?? "")
        : name === "credits"
          ? "EA"
          : "";
  const text = (
    f: Record<string, unknown>,
    name: "name" | "credits" | "credits_url",
  ) =>
    typeof f[name] === "string"
      ? (f[name] as string)
      : (data?.[name] as string | null) || gameText(name);
  const own = (f: Record<string, unknown>, name: "name" | "credits") => {
    const value = text(f, name).trim();
    return value === gameText(name) ? "" : value;
  };
  const hasPending = !!(
    pending.mesh ||
    pending.texture ||
    pending.remove.length ||
    pending.picture
  );
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ["equipment", "player", "team"],
    save: async (f) => {
      let saved = await api.saveEquipment(kind, code, {
        name: own(f.fields, "name"),
        credits: own(f.fields, "credits"),
        credits_url: text(f.fields, "credits_url") || null,
      });
      if (pending.mesh || pending.texture || pending.remove.length)
        saved = await api.setEquipmentFiles(kind, code, {
          mesh: pending.mesh,
          texture: pending.texture,
          remove: pending.remove,
        });
      if (pending.picture === "remove")
        saved = await api.removeEquipmentPicture(kind, code);
      else if (pending.picture)
        saved = await api.setEquipmentPicture(kind, code, pending.picture.data);
      if (hide.pending !== null)
        saved = await api.setEquipmentHidden(kind, code, hide.pending);
      clearPending();
      return saved;
    },
    reset: async () => {
      clearPending();
      return (await api.deleteEquipment(kind, code)) as Equipment;
    },
    extraDirty: hasPending || hide.pending !== null,
    onDiscard: clearPending,
    invalid: (f) => isNew && !text(f.fields, "name").trim(),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteEquipment(kind, code),
    onSuccess: () => {
      for (const key of ["equipment", "player", "team", "status"])
        void qc.invalidateQueries({ queryKey: [key] });
      toast.success(t("equipment.deleted"));
      navigate(back.to, { state: back.state });
    },
    onError: (e: Error) => {
      setDeleting(false);
      toast.error(e.message);
    },
  });
  if (isLoading) return <LoadingBlock />;
  if (!data)
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        <p className="text-muted-foreground">
          {error?.message ?? k("notFound")}
        </p>
      </div>
    );

  const fields = entity.form.fields as Record<string, unknown>;
  const name = text(fields, "name");
  const title = name.trim() || nameOf(data);
  const has = (file: string) =>
    !pending.remove.includes(file) && data.files.includes(file);
  const pickFile = (file: "mesh" | "texture") => async (f: File) => {
    try {
      const b64 = await readPicture(f);
      setPending((p) => ({
        ...p,
        [file]: b64,
        remove: p.remove.filter((r) => r !== file),
      }));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const pickPicture = async (f: File) => {
    try {
      const b64 = await readPicture(f);
      setPending((p) => ({
        ...p,
        picture: { data: b64, url: URL.createObjectURL(f) },
      }));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const ownPicture =
    pending.picture === "remove"
      ? false
      : !!pending.picture || data.picture !== null;
  const shownUrl =
    pendingUrl ??
    (pending.picture === "remove"
      ? null
      : equipmentPictureUrl(kind, code, data.picture ?? data.version));
  const fileKinds =
    kind === "glove" ? (["texture"] as const) : (["mesh", "texture"] as const);
  const sent =
    data.files.length > 0 &&
    data.files.some((f) => !pending.remove.includes(f));
  const missing = isNew && fileKinds.some((f) => !has(f) && !pending[f]);

  return (
    <div className="flex flex-col gap-4 xl:h-full">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          <EquipmentThumb kind={kind} item={data} className="h-10 w-20" />
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="min-w-0 text-2xl font-semibold break-words">
                {title}
              </h1>
              <span className="shrink-0 text-sm text-muted-foreground tabular-nums">
                {t("equipment.code", { code })}
              </span>
              {!isNew && <OriginalBadge edited={data.edited} />}
              {hide.hidden && <OutOfPatchBadge alert />}
            </div>
            <EntryDates entry={data} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-between">
          <div className="flex flex-wrap gap-2">
            <EditActions edited={!isNew && data.edited} entity={entity} />
            <ExportButton kind={kind} id={code} dirty={entity.dirty} />
            {isNew && (
              <>
                <HideButton
                  variant="outline"
                  hidden={hide.hidden}
                  onToggle={hide.toggle}
                  hideHint={k("hideHint")}
                  showHint={k("showHint")}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDeleting(true)}
                >
                  <Trash2 /> {k("delete")}
                </Button>
              </>
            )}
          </div>
          <EquipmentWarnings warnings={warningsOf(data)} />
        </div>
      </div>

      <div className="flex flex-col gap-4 xl:min-h-0 xl:flex-1 xl:flex-row">
        <div className="flex min-w-0 flex-col gap-4 xl:min-h-0 xl:flex-1">
          <Section className="shrink-0" title={t("equipment.data")}>
            <div className="grid gap-4">
              <div className="space-y-1.5">
                <Label>{k("name")}</Label>
                <Input
                  value={name}
                  maxLength={60}
                  autoFocus={isNew && !name}
                  onChange={(e) => entity.setField("name", e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {t(
                    kind === "glove" && !data.listed
                      ? "gloves.nameHintNew"
                      : (`${KINDS[kind].t}.nameHint` as MessageKey),
                  )}
                </p>
                {isNew && !name.trim() && (
                  <p className="text-xs text-destructive">
                    {t("equipment.nameRequired")}
                  </p>
                )}
              </div>
              <div className="space-y-1.5">
                <Label>{k("credits")}</Label>
                <Input
                  value={text(fields, "credits")}
                  maxLength={200}
                  onChange={(e) => entity.setField("credits", e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {k("creditsHint")}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label>{t("equipment.creditsLink")}</Label>
                <Input
                  type="url"
                  value={text(fields, "credits_url")}
                  maxLength={200}
                  placeholder="https://"
                  onChange={(e) =>
                    entity.setField("credits_url", e.target.value)
                  }
                />
                <p className="text-xs text-muted-foreground">
                  {t("equipment.creditsLinkHint")}
                </p>
              </div>
              <ListedNote kind={kind} item={data} />
              {kind === "glove" && (
                <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                  <Info className="mt-0.5 size-3.5 shrink-0" />
                  <span>{t("gloves.onlyGoalkeepersRule")}</span>
                </p>
              )}
            </div>
          </Section>

          <Section
            className="shrink-0"
            title={k("files")}
            description={
              isNew ? k("filesDescription") : k("filesOriginalDescription")
            }
          >
            <div className="grid gap-4">
              {fileKinds.map((file) => (
                <FileField
                  key={file}
                  label={k(file)}
                  hint={k(`${file}Hint`)}
                  has={has(file)}
                  pending={!!pending[file]}
                  fallback={isNew ? undefined : k("gameFile")}
                  onPick={pickFile(file)}
                />
              ))}
              {!isNew && sent && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-fit"
                  onClick={() =>
                    setPending((p) => ({
                      ...p,
                      mesh: undefined,
                      texture: undefined,
                      remove: [...data.files],
                    }))
                  }
                >
                  <RotateCcw />{" "}
                  {kind === "glove" ? k("gameFileBack") : k("gameFilesBack")}
                </Button>
              )}
              {missing && (
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  {t("equipment.missingFilesWarning")}
                </p>
              )}
              {(pending.mesh || pending.texture) && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  {t("equipment.filesPending")}
                </p>
              )}
            </div>
          </Section>

          <Section
            scroll
            className="xl:min-h-48 xl:flex-1"
            title={k("wearers")}
            description={
              isNew
                ? k("wearersDescription")
                : k("wearersOriginal", { count: data.wearer_count })
            }
          >
            {data.wearers.length ? (
              <div className="space-y-3">
                {[
                  {
                    key: "project",
                    title: t("list.originProject"),
                    items: data.wearers.filter((w) => w.is_new),
                  },
                  {
                    key: "game",
                    title: t("list.originOriginal"),
                    items: data.wearers.filter((w) => !w.is_new),
                  },
                ]
                  .filter((g) => g.items.length)
                  .map((g, i) => (
                    <div
                      key={g.key}
                      className={
                        i ? "space-y-1.5 border-t pt-3" : "space-y-1.5"
                      }
                    >
                      <p className="text-xs font-medium text-muted-foreground">
                        {g.title} ({g.items.length})
                      </p>
                      <ul className="grid gap-1 text-sm sm:grid-cols-2 xl:grid-cols-3">
                        {g.items.map((w) => (
                          <li key={w.id} className="truncate">
                            <Link
                              to={
                                kind === "ball"
                                  ? `/teams/${w.id}`
                                  : `/players/${w.id}?tab=accessories`
                              }
                              state={from.state}
                              className="underline-offset-4 hover:underline"
                            >
                              {w.name}
                            </Link>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{k("noWearers")}</p>
            )}
          </Section>
        </div>
        <div className="order-first flex min-w-0 flex-col gap-4 xl:order-none xl:min-h-0 xl:flex-1">
          <Section
            className="shrink-0"
            title={k("thumbnail")}
            description={k("thumbnailHint")}
          >
            <div className="space-y-3">
              <div
                className="flex h-40 w-full cursor-pointer items-center justify-center rounded-lg bg-gradient-to-b from-muted to-background"
                onClick={() => pictureInput.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const f = e.dataTransfer.files[0];
                  if (f) void pickPicture(f);
                }}
                title={t("image.clickOrDrop")}
              >
                {shownUrl ? (
                  <img
                    src={shownUrl}
                    alt=""
                    className="max-h-full max-w-full object-contain"
                  />
                ) : (
                  <ImageOff className="size-8 text-muted-foreground" />
                )}
              </div>
              <input
                ref={pictureInput}
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.bmp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  e.target.value = "";
                  if (f) void pickPicture(f);
                }}
              />
              <p className="text-center text-xs text-muted-foreground">
                {ownPicture ? t("equipment.ownPicture") : k("thumbnailAuto")}
              </p>
              {pending.picture && (
                <p className="text-center text-xs text-amber-600 dark:text-amber-400">
                  {t(
                    pending.picture === "remove"
                      ? "equipment.pictureRemovePending"
                      : "equipment.picturePending",
                  )}
                </p>
              )}
              <div className="flex justify-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => pictureInput.current?.click()}
                >
                  <Upload /> {t("common.replace")}
                </Button>
                {ownPicture && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setPending((p) => ({
                        ...p,
                        picture: data.picture !== null ? "remove" : undefined,
                      }))
                    }
                  >
                    <Trash2 /> {t("common.remove")}
                  </Button>
                )}
              </div>
              {kind === "ball" && (
                <p className="text-xs text-muted-foreground">
                  {t("balls.menuPictureHint")}
                </p>
              )}
            </div>
          </Section>
          <div className="flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card xl:min-h-64 xl:flex-1">
            <div className="aspect-[4/3] max-h-[50vh] w-full bg-gradient-to-b from-muted to-background xl:aspect-auto xl:max-h-none xl:min-h-0 xl:flex-1">
              <EquipmentPreview
                kind={kind}
                code={code}
                version={data.version}
                empty={
                  missing && !data.files.length
                    ? k("previewNeedsFiles")
                    : undefined
                }
              />
            </div>
            <p
              className="px-4 py-2 text-center text-xs text-muted-foreground"
              title={t("equipment.previewControls")}
            >
              {k("previewLabel")}
            </p>
          </div>
        </div>
      </div>

      <AlertDialog
        open={deleting}
        onOpenChange={(o) => !remove.isPending && setDeleting(o)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {k("deleteTitle", { count: 1 })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {data.wearer_count ? k("deleteWorn") : k("deleteDescription")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {data.wearer_count > 0 && (
            <ul className="max-h-40 overflow-auto text-sm">
              {data.wearers.map((w) => (
                <li key={w.id}>{w.name}</li>
              ))}
            </ul>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={(e) => (e.preventDefault(), remove.mutate())}
            >
              {remove.isPending ? (
                <Loader2 className="animate-spin" />
              ) : (
                <Trash2 />
              )}{" "}
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
