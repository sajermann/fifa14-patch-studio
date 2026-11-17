import { Loader2 } from 'lucide-react'
import { useI18n } from '@/i18n'

export function LoadingBlock() {
  const { t } = useI18n()
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> {t('common.loading')}
    </div>
  )
}
