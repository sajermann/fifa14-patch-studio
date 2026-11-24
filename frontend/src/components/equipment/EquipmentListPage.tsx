import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import type { EquipmentKind } from "@/api/types";
import { DateCells, DateHeads } from "@/components/common/dates";
import { OriginalBadge } from "@/components/common/detail";
import { HideButton, OutOfPatchBadge } from "@/components/common/HideButton";
import {
  BulkActions,
  RowCheckbox,
  SelectAllCheckbox,
  SelectAllDialog,
  useListSelection,
} from "@/components/common/selection";
import {
  EquipmentThumb,
  EquipmentWarnings,
  equipmentPath,
  KINDS,
  useEquipmentList,
  useEquipmentName,
  useEquipmentWarnings,
  useKindText,
} from "@/components/equipment/equipment";
import { Button } from "@/components/ui/button";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useI18n, type MessageKey } from "@/i18n";
import { useFrom } from "@/lib/back";
import {
  ALL,
  FilterBar,
  FilterSelect,
  LIST_PAGE,
  ScrollTable,
  SearchInput,
  SortHead,
  useLocalSort,
} from "@/lib/list";
import { toast } from "@/lib/notify";

/** The boots, gloves or balls (the Street Studio's BootsPage / GlovesPage / BallsPage): the user's, then the game's
 * (original or edited), each with its picture, credits, who wears it and its code. */
export function EquipmentListPage({ kind }: { kind: EquipmentKind }) {
  const { t } = useI18n();
  const k = useKindText(kind);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const nameOf = useEquipmentName();
  const warningsOf = useEquipmentWarnings();
  const navKey = `nav.${KINDS[kind].t}` as MessageKey;
  const from = useFrom({ key: navKey });
  const { data, isLoading, error } = useEquipmentList(kind);
  const [q, setQ] = useState("");
  const [origin, setOrigin] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const query = q.trim().toLowerCase();
  const filtered = (data?.items ?? []).filter(
    (e) =>
      (nameOf(e).toLowerCase().includes(query) ||
        (e.credits || (e.is_new ? "" : "EA")).toLowerCase().includes(query) ||
        String(e.code).includes(query)) &&
      (origin === ALL ||
        (origin === "project"
          ? e.is_new
          : origin === "edited"
            ? e.edited
            : !e.is_new)) &&
      (status === ALL || (status === "hidden" ? e.hidden : !e.hidden)),
  );
  const sorted = useLocalSort(filtered, {
    name: (e) => nameOf(e),
    credits: (e) => e.credits || (e.is_new ? "" : "EA"),
    wearers: (e) => e.wearer_count,
    id: (e) => e.code,
    created_at: (e) => e.created_at,
    updated_at: (e) => e.updated_at,
  });
  const items = sorted.rows;
  // the user's items can be deleted, the game's edited ones restored, in bulk
  const pickable = items.filter((e) => e.is_new || e.edited).map((e) => e.code);
  const selection = useListSelection(pickable, pickable);
  const created = (data?.items ?? []).filter((e) => e.is_new).length;
  const create = useMutation({
    mutationFn: () =>
      api.createEquipment(kind, { name: k("defaultName", { n: created + 1 }) }),
    onSuccess: (item) => {
      void qc.invalidateQueries({ queryKey: ["equipment", kind] });
      navigate(equipmentPath(kind, item.code), { state: from.state });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const hide = useMutation({
    mutationFn: ({ code, hidden }: { code: number; hidden: boolean }) =>
      api.setEquipmentHidden(kind, code, hidden),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ["equipment", kind] }),
    onError: (e: Error) => toast.error(e.message),
  });
  const total = created + (data?.free ?? 0);
  return (
    <div className={LIST_PAGE}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t(navKey)}</h1>
          <p className="text-sm text-muted-foreground">{k("description")}</p>
        </div>
        <div className="flex items-center gap-3">
          {data && (
            <span
              className="text-sm text-muted-foreground tabular-nums"
              title={k("slotsHint", { total })}
            >
              {k("slots", { used: created, total })}
            </span>
          )}
          <Button
            disabled={create.isPending || (!!data && !data.free)}
            title={data && !data.free ? k("slotsFull", { total }) : undefined}
            onClick={() => create.mutate()}
          >
            {create.isPending ? <Loader2 className="animate-spin" /> : <Plus />}{" "}
            {k("new")}
          </Button>
        </div>
      </div>
      <FilterBar
        active={!!q || origin !== ALL || status !== ALL}
        onClear={() => (setQ(""), setOrigin(ALL), setStatus(ALL))}
      >
        <SearchInput value={q} onChange={setQ} placeholder={k("search")} />
        <FilterSelect
          value={origin}
          onChange={setOrigin}
          allLabel={t("list.originAll")}
          options={[
            { value: "project", label: t("equipment.originProject") },
            { value: "original", label: t("list.originOriginal") },
            { value: "edited", label: t("equipment.originEdited") },
          ]}
        />
        <FilterSelect
          value={status}
          onChange={setStatus}
          allLabel={t("equipment.statusAll")}
          options={[
            { value: "in", label: t("equipment.statusInPatch") },
            { value: "hidden", label: t("equipment.statusHidden") },
          ]}
        />
        <BulkActions
          kind={kind}
          selection={selection}
          invalidate={["equipment", "player", "team"]}
        />
      </FilterBar>
      <ScrollTable loading={isLoading}>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8">
              <SelectAllCheckbox selection={selection} />
            </TableHead>
            <TableHead className="w-16" />
            <SortHead
              field="name"
              label={t("col.name")}
              state={sorted.state}
              className="w-full"
            />
            <SortHead
              field="credits"
              label={k("colCredits")}
              state={sorted.state}
              className="text-right"
            />
            <SortHead
              field="wearers"
              label={k("colWearers")}
              state={sorted.state}
              className="text-center"
            />
            <SortHead
              field="id"
              label="ID"
              state={sorted.state}
              className="text-center"
            />
            <DateHeads sort={sorted.state} />
            <TableHead className="w-28" />
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((e) => (
            <TableRow
              key={e.code}
              className={
                e.is_new || e.edited ? undefined : "text-muted-foreground"
              }
            >
              <TableCell>
                {(e.is_new || e.edited) && (
                  <RowCheckbox selection={selection} value={e.code} />
                )}
              </TableCell>
              <TableCell>
                <EquipmentThumb kind={kind} item={e} />
              </TableCell>
              <TableCell data-grow>
                <span className="flex flex-wrap items-center gap-2">
                  <Link
                    to={equipmentPath(kind, e.code)}
                    state={from.state}
                    title={e.is_new ? undefined : k("editOriginalHint")}
                    className={
                      e.hidden
                        ? "font-medium text-muted-foreground underline-offset-4 hover:underline"
                        : "font-medium text-foreground underline-offset-4 hover:underline"
                    }
                  >
                    {nameOf(e)}
                  </Link>
                  {!e.is_new && <OriginalBadge edited={e.edited} />}
                  {e.hidden && <OutOfPatchBadge />}
                </span>
              </TableCell>
              <TableCell className="max-w-48 truncate text-right text-muted-foreground">
                {e.credits || (e.is_new ? "—" : "EA")}
              </TableCell>
              <TableCell
                className="text-center tabular-nums"
                title={e.wearers
                  .slice(0, 30)
                  .map((w) => w.name)
                  .join(", ")}
              >
                {e.wearer_count || "—"}
              </TableCell>
              <TableCell className="text-center tabular-nums">
                {e.code}
              </TableCell>
              <DateCells entry={e} />
              <TableCell>
                {e.is_new && (
                  <HideButton
                    hidden={e.hidden}
                    onToggle={() =>
                      hide.mutate({ code: e.code, hidden: !e.hidden })
                    }
                    hideHint={k("hideHint")}
                    showHint={k("showHint")}
                  />
                )}
              </TableCell>
              <TableCell>
                <EquipmentWarnings warnings={warningsOf(e)} />
              </TableCell>
            </TableRow>
          ))}
          {!isLoading && items.length === 0 && (
            <TableRow>
              <TableCell
                colSpan={10}
                className="py-10 text-center text-muted-foreground"
              >
                {error
                  ? k("originalsFailed", { error: (error as Error).message })
                  : k("noneFiltered")}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </ScrollTable>
      <SelectAllDialog selection={selection} />
    </div>
  );
}
