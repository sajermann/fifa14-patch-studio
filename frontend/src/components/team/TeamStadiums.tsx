import { useState } from 'react'
import type { StadiumInfo } from '@/api/types'
import { Stadium3D, StadiumDatabase, StadiumDetails } from '@/components/common/stadium'
import { useI18n } from '@/i18n'

/** The team's stadium tab, read-only for now: the same as the extractor's (3D preview, data, pictures, files and the
 * database row). */
function TeamStadium({ stadium, customName }: { stadium: StadiumInfo; customName: string | null }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="space-y-4">
      <Stadium3D stadium={stadium} open={open} setOpen={setOpen} className={open ? 'h-[70vh]' : undefined} />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <StadiumDetails stadium={stadium} customName={customName} />
        <StadiumDatabase stadium={stadium} className="xl:grid-cols-1" />
      </div>
    </div>
  )
}

export function TeamStadiums({ stadiums, customName }: { stadiums: StadiumInfo[]; customName: string | null }) {
  const { t } = useI18n()
  if (!stadiums.length) return <p className="py-6 text-sm text-muted-foreground">{t('teams.noStadium')}</p>
  return (
    <div className="space-y-4">
      {stadiums.map((s) => (
        <TeamStadium key={s.id} stadium={s} customName={stadiums.length === 1 ? customName : null} />
      ))}
    </div>
  )
}
