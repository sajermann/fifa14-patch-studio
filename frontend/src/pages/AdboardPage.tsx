import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, Loader2, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '@/api/client'
import { AdboardThumb, GameBoardWarning, useAdboardName, useAdboards } from '@/components/adboard/AdboardChoice'
import { EntryDates } from '@/components/common/dates'
import { OriginalBadge, Section } from '@/components/common/detail'
import { EditActions, useEntityForm } from '@/components/common/edit'
import { EntityIssues } from '@/components/common/form'
import { HideButton, OutOfPatchBadge, usePendingHide } from '@/components/common/HideButton'
import { readPicture } from '@/components/common/pictures'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useI18n } from '@/i18n'
import { BackButton, useBack, useFrom } from '@/lib/back'
import { toast } from '@/lib/notify'
import { useToken } from '@/state/queries'

/** A picture chosen and not saved yet (base64 + a local address to show it), or 'remove'. */
type PendingPicture = { data: string; url: string } | 'remove' | null

/** The board picture as the game gets it, with its bands numbered (one ad per band, top to bottom). */
function BandsPreview({ url, bands }: { url: string | null; bands: number }) {
  const { t } = useI18n()
  if (!url)
    return (
      <div className="flex aspect-[1/2] w-64 items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
        {t('adboards.noPicture')}
      </div>
    )
  return (
    <div className="flex items-stretch gap-1">
      <div className="flex w-6 flex-col">
        {Array.from({ length: bands }, (_, i) => (
          <span key={i} className="flex flex-1 items-center justify-end pr-1 text-[10px] text-muted-foreground tabular-nums">
            {i + 1}
          </span>
        ))}
      </div>
      <img src={url} alt="" className="aspect-[1/2] w-64 rounded-lg border object-fill" />
    </div>
  )
}

/** One advertising board: a board the user created (name, picture, hide, delete) or one of the game's (its picture
 * can be replaced, which changes it where the game shows it, and restored), with the teams and leagues it is on and a
 * Copy button. Saved as the other screens (Save / Discard); the links are made on the team and league screens. */
export function AdboardPage() {
  const { t } = useI18n()
  const id = Number(useParams().id)
  const token = useToken()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const nameOf = useAdboardName()
  const queryKey = ['adboard', token, id]
  const { data, isLoading, error } = useQuery({ queryKey, queryFn: () => api.adboard(id), enabled: !!token })
  const info = useAdboards().data
  const size = info?.size ?? [512, 1024]
  const bands = info?.bands ?? 16
  const back = useBack({ to: '/adboards', label: { key: 'nav.adboards' } })
  const from = useFrom(data ? nameOf(data) : { key: 'nav.adboards' })
  const hide = usePendingHide(data?.hidden)
  const [pending, setPending] = useState<PendingPicture>(null)
  const [deleting, setDeleting] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const pendingUrl = pending && pending !== 'remove' ? pending.url : null
  useEffect(() => () => void (pendingUrl && URL.revokeObjectURL(pendingUrl)), [pendingUrl])
  const clearPending = () => {
    setPending(null)
    hide.clear()
  }
  const isNew = !!data?.is_new
  const entity = useEntityForm({
    data,
    queryKey,
    invalidate: ['adboards', 'team', 'league'],
    save: async (f) => {
      const name = typeof f.fields.name === 'string' ? f.fields.name : (data?.name ?? '')
      let saved = await api.saveAdboard(id, {
        name,
        picture: pending && pending !== 'remove' ? pending.data : undefined,
        remove_picture: pending === 'remove',
      })
      if (hide.pending !== null) saved = await api.setAdboardHidden(id, hide.pending)
      clearPending()
      return saved
    },
    reset: () => {
      clearPending()
      return api.resetAdboard(id)
    },
    extraDirty: pending !== null || hide.pending !== null,
    onDiscard: clearPending,
    invalid: (f) => isNew && !(typeof f.fields.name === 'string' ? f.fields.name : (data?.name ?? '')).trim(),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteAdboard(id),
    onSuccess: () => {
      for (const k of ['adboards', 'team', 'league', 'status']) void qc.invalidateQueries({ queryKey: [k] })
      toast.success(t('adboards.deleted'))
      navigate(back.to, { state: back.state })
    },
    onError: (e: Error) => {
      setDeleting(false)
      toast.error(e.message)
    },
  })
  const copy = useMutation({
    mutationFn: () => api.createAdboard({ name: t('adboards.copyName', { name: data ? nameOf(data) : '' }), copy_of: id }),
    onSuccess: (board) => {
      void qc.invalidateQueries({ queryKey: ['adboards'] })
      toast.success(t('adboards.copied'))
      navigate(`/adboards/${board.id}`, { state: from.state })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  if (isLoading) return <LoadingBlock />
  if (!data)
    return (
      <div className="space-y-2">
        <BackButton back={back} />
        <p className="text-muted-foreground">{error?.message ?? t('list.empty')}</p>
      </div>
    )
  const name = typeof entity.form.fields.name === 'string' ? entity.form.fields.name : data.name
  const savedUrl = data.picture !== null ? `/api/image/adboard/${data.id}?v=${data.picture}` : null
  const shownUrl = pending === 'remove' ? (isNew ? null : `/api/image/adboard/${data.id}?game_only=true`) : (pendingUrl ?? savedUrl)
  const hasPicture = pending === 'remove' ? false : !!pending || data.picture !== null
  // the user's own picture (a game board's game picture is not one: Remove only takes the user's away)
  const ownSaved = isNew ? data.picture !== null : data.edited
  const hasOwn = pending === 'remove' ? false : !!pending || ownSaved
  const title = isNew ? name.trim() || data.name : nameOf(data)
  const pick = async (file: File) => {
    try {
      setPending({ data: await readPicture(file), url: URL.createObjectURL(file) })
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  return (
    <div className="space-y-4">
      <BackButton back={back} />
      <div className="flex flex-wrap justify-between gap-x-4 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          {shownUrl ? <img src={shownUrl} alt="" className="aspect-[1/2] w-12 shrink-0 rounded border object-fill" /> : <AdboardThumb board={undefined} width={48} />}
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
              <h1 className="min-w-0 text-2xl font-semibold break-words">{title}</h1>
              <span className="shrink-0 text-sm text-muted-foreground tabular-nums">ID {data.id}</span>
              {!isNew && <OriginalBadge edited={data.edited} />}
              {hide.hidden && <OutOfPatchBadge alert />}
            </div>
            <EntryDates entry={data} />
          </div>
        </div>
        <div className="flex flex-col items-end justify-between">
          <div className="flex flex-wrap gap-2">
          <EditActions edited={!isNew && data.edited} entity={entity} />
          <Button variant="outline" size="sm" title={t('adboards.copyHint')} disabled={copy.isPending || data.picture === null || entity.dirty} onClick={() => copy.mutate()}>
            {copy.isPending ? <Loader2 className="animate-spin" /> : <Copy />} {t('adboards.copy')}
          </Button>
          {isNew && (
            <>
              <HideButton variant="outline" hidden={hide.hidden} onToggle={hide.toggle} hideHint={t('adboards.hideHint')} showHint={t('adboards.showHint')} />
              <Button variant="outline" size="sm" onClick={() => setDeleting(true)}>
                <Trash2 /> {t('common.delete')}
              </Button>
            </>
          )}
          </div>
          <EntityIssues kind="adboard" id={data.id} />
        </div>
      </div>

      {/* the data on the left; the picture on the right, as narrow as the picture, with its buttons below it (the
          player's photo card) */}
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
        <div className="space-y-4">
          {isNew ? (
            <Section title={t('adboards.name')} description={t('adboards.nameHint')}>
              <Input value={name} maxLength={60} onChange={(e) => entity.setField('name', e.target.value)} />
            </Section>
          ) : (
            <Section title={t('adboards.gameTitle')} description={t('adboards.gameHint')}>
              <GameBoardWarning board={data} />
            </Section>
          )}
          <Section title={t('adboards.usedBy')} description={t('adboards.usedByHint')}>
            {data.teams.length || data.leagues.length ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-1 text-xs text-muted-foreground">{t('adboards.colTeams')}</p>
                  <ul className="space-y-1 text-sm">
                    {data.teams.map((tm) => (
                      <li key={tm.id}>
                        <Link to={`/teams/${tm.id}?tab=adboard`} state={from.state} className="underline-offset-4 hover:underline">
                          {tm.name}
                        </Link>
                      </li>
                    ))}
                    {!data.teams.length && <li className="text-muted-foreground">—</li>}
                  </ul>
                </div>
                <div>
                  <p className="mb-1 text-xs text-muted-foreground">{t('adboards.colLeagues')}</p>
                  <ul className="space-y-1 text-sm">
                    {data.leagues.map((lg) => (
                      <li key={lg.id}>
                        <Link to={`/leagues/${lg.id}?tab=adboard`} state={from.state} className="underline-offset-4 hover:underline">
                          {lg.name}
                        </Link>
                      </li>
                    ))}
                    {!data.leagues.length && <li className="text-muted-foreground">—</li>}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('adboards.notUsed')}</p>
            )}
          </Section>
        </div>
        <Section
          className="lg:w-[22rem]"
          title={t('adboards.picture')}
          description={t('adboards.pictureHint', { width: size[0], height: size[1], bands, band: size[1] / bands })}
        >
          <div className="space-y-3">
            <div
              className="mx-auto w-fit cursor-pointer"
              onClick={() => input.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                const f = e.dataTransfer.files[0]
                if (f) void pick(f)
              }}
              title={t('image.clickOrDrop')}
            >
              <BandsPreview url={shownUrl} bands={bands} />
            </div>
            <input
              ref={input}
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.bmp,.dds"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                e.target.value = ''
                if (file) void pick(file)
              }}
            />
            {pending && <p className="text-center text-xs text-amber-600 dark:text-amber-400">{t(pending === 'remove' ? 'adboards.pictureRemovePending' : 'adboards.picturePending')}</p>}
            {shownUrl && (
              <div className="flex justify-center gap-2">
                <Button variant="outline" size="sm" onClick={() => input.current?.click()}>
                  <Upload /> {t('common.replace')}
                </Button>
                {hasOwn && (
                  <Button variant="outline" size="sm" onClick={() => setPending(ownSaved ? 'remove' : null)}>
                    <Trash2 /> {t('common.remove')}
                  </Button>
                )}
              </div>
            )}
            {pending && pending !== 'remove' && !isNew && <GameBoardWarning board={{ ...data, edited: true }} />}
            {isNew && !hasPicture && <p className="text-sm text-amber-600 dark:text-amber-400">{t('adboards.noPictureWarning')}</p>}
            <p className="text-xs text-muted-foreground">{t('adboards.pictureHowTo', { bands })}</p>
          </div>
        </Section>
      </div>

      <AlertDialog open={deleting} onOpenChange={(o) => !remove.isPending && setDeleting(o)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('adboards.deleteTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('adboards.deleteText')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={remove.isPending} onClick={(e) => (e.preventDefault(), remove.mutate())}>
              {remove.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />} {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
