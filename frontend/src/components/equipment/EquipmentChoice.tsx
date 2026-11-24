import { AlertTriangle, Info, Repeat } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Equipment, EquipmentKind, FieldValue } from "@/api/types";
import { Section } from "@/components/common/detail";
import {
  PickerDialog,
  type PickerGroup,
} from "@/components/common/PickerDialog";
import {
  equipmentPath,
  EquipmentThumb,
  useEquipmentList,
  useEquipmentName,
} from "@/components/equipment/equipment";
import { ListedNote } from "@/components/equipment/EquipmentEditPage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useI18n, type MessageKey } from "@/i18n";
import { useFrom } from "@/lib/back";

const FIELD: Record<EquipmentKind, string> = {
  boot: "shoetypecode",
  glove: "gkglovetypecode",
  ball: "balltype",
};
const TEXTS: Record<EquipmentKind, string> = {
  boot: "playerBoots",
  glove: "playerGloves",
  ball: "teamBall",
};
const GOALKEEPER = 0; // preferredposition1 of a goalkeeper

/** What a player wears (boot, goalkeeper glove) or a team plays with (ball), picked from the project's and the
 * game's items (the Street Studio's PlayerBoots / PlayerGloves card): saved with the player or the team (Save). */
export function EquipmentChoice({
  kind,
  owner,
  values,
  fields,
  setField,
  preferredPosition,
}: {
  kind: EquipmentKind;
  owner: string;
  values: Record<string, FieldValue>;
  fields: Record<string, FieldValue>;
  setField: (name: string, value: number | null) => void;
  /** A player's preferred position (as saved or being edited): the glove only shows on a goalkeeper. */
  preferredPosition?: number | null;
}) {
  const { t } = useI18n();
  const tx = (key: string, vars?: Record<string, string | number>) =>
    t(`${TEXTS[kind]}.${key}` as MessageKey, vars);
  const nameOf = useEquipmentName();
  const items = useEquipmentList(kind).data?.items ?? [];
  const from = useFrom(owner);
  const [picking, setPicking] = useState(false);
  const [query, setQuery] = useState("");
  const field = FIELD[kind];
  const picked = typeof fields[field] === "number";
  const code = (picked ? fields[field] : values[field]) as
    number | null | undefined;
  const item = items.find((e) => e.code === code);
  const name = item ? nameOf(item) : code ? `Original ${code}` : tx("none");

  const q = query.trim().toLowerCase();
  const match = (e: Equipment) =>
    !q ||
    nameOf(e).toLowerCase().includes(q) ||
    e.credits.toLowerCase().includes(q) ||
    String(e.code).includes(q);
  const entry = (e: Equipment) => ({
    key: e.code,
    icon: <EquipmentThumb kind={kind} item={e} />,
    title: nameOf(e),
    subtitle: (
      <span>
        {t("equipment.code", { code: e.code })}
        {e.credits && ` · ${e.credits}`}
        {!e.listed && ` · ${t("gloves.notListed")}`}
      </span>
    ),
    disabled: e.is_new && !e.complete,
  });
  const groups: PickerGroup<number>[] = [
    {
      label: t("playerBoots.groupProject"),
      items: items.filter((e) => e.is_new && !e.hidden && match(e)).map(entry),
    },
    {
      label: t("playerBoots.groupGame"),
      items: items.filter((e) => !e.is_new && match(e)).map(entry),
    },
  ];
  const notKeeper =
    kind === "glove" &&
    code != null &&
    code > 0 &&
    preferredPosition != null &&
    preferredPosition !== GOALKEEPER;

  return (
    <Section
      className="min-w-0"
      title={tx("title")}
      description={tx("description")}
      action={
        picked && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setField(field, null)}
          >
            <Repeat /> {t("playerBoots.useDefault")}
          </Button>
        )
      }
    >
      <div className="grid grid-cols-1 gap-3">
        <div className="flex items-center gap-3 rounded-lg border p-3">
          <EquipmentThumb
            kind={kind}
            item={item}
            code={code || undefined}
            className="h-12 w-20"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">
              {code ? (
                <Link
                  className="underline-offset-2 hover:underline"
                  to={equipmentPath(kind, code)}
                  state={from.state}
                >
                  {name}
                </Link>
              ) : (
                name
              )}
              {!picked && (
                <Badge variant="outline" className="ml-2 font-normal">
                  {t("common.default")}
                </Badge>
              )}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {code ? t("equipment.code", { code }) : tx("noneHint")}
              {item?.credits &&
                ` · ${t("playerBoots.credits", { credits: item.credits })}`}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="shrink-0"
            onClick={() => {
              setQuery("");
              setPicking(true);
            }}
          >
            {t("playerBoots.change")}
          </Button>
        </div>
        {item?.hidden && (
          <p className="flex items-start gap-1 text-xs text-amber-600 dark:text-amber-500">
            <AlertTriangle className="mt-0.5 size-3 shrink-0" />
            <span>{t("equipment.pickedHidden")}</span>
          </p>
        )}
        {notKeeper && (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-400">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{t("playerGloves.notGoalkeeper")}</span>
          </div>
        )}
        {item && <ListedNote kind={kind} item={item} />}
        {kind === "glove" && !notKeeper && (
          <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            <span>{t("gloves.onlyGoalkeepersRule")}</span>
          </p>
        )}
      </div>
      <PickerDialog<number>
        open={picking}
        onOpenChange={setPicking}
        title={tx("pickTitle")}
        description={tx("pickDescription")}
        placeholder={t(
          `${kind === "boot" ? "boots" : kind === "glove" ? "gloves" : "balls"}.search` as MessageKey,
        )}
        query={query}
        onQuery={setQuery}
        groups={groups}
        empty={t(
          `${kind === "boot" ? "boots" : kind === "glove" ? "gloves" : "balls"}.noneFiltered` as MessageKey,
        )}
        actionLabel={t("playerBoots.pick")}
        onPick={(key) => {
          setField(field, key === values[field] ? null : key);
          setPicking(false);
        }}
      />
    </Section>
  );
}
