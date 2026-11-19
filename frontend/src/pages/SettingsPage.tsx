import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { api } from '@/api/client'
import type { Config } from '@/api/types'
import { Facts, Section } from '@/components/common/detail'
import { FacePackFolders } from '@/components/player/FacePackFolders'
import { LANGS, useI18n, type Lang } from '@/i18n'
import { toast } from '@/lib/notify'
import { APP_NAME, APP_VERSION, AUTHOR_GITHUB, AUTHOR_NAME, REPO_URL } from '@/lib/about'
import { useTheme } from '@/lib/theme'
import { useOptions, useStatus } from '@/state/queries'

export function SettingsPage() {
  const { t, lang, setLang } = useI18n()
  const { theme, setTheme } = useTheme()
  const status = useStatus().data
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (fields: Partial<Config>) => api.saveSettings(fields),
    onSuccess: () => qc.invalidateQueries(),
    onError: (e: Error) => toast.error(e.message),
  })
  const languages = useOptions().data?.languages ?? []
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">{t('settings.title')}</h1>
      <Section title={t('settings.interface')}>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <p className="text-sm font-medium">{t('settings.language')}</p>
            <Select
              value={lang}
              onValueChange={(v) => setLang(v as Lang)} // saved in the backend by LanguageSync
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGS.map((l) => (
                  <SelectItem key={l.value} value={l.value}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-medium">{t('settings.theme')}</p>
            <Select value={theme} onValueChange={setTheme}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">{t('prefs.themeSystem')}</SelectItem>
                <SelectItem value="light">{t('prefs.themeLight')}</SelectItem>
                <SelectItem value="dark">{t('prefs.themeDark')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </Section>
      <Section title={t('settings.gameNames')}>
        <p className="mb-3 text-sm text-muted-foreground">{t('settings.gameNamesHint')}</p>
        <Select value={status?.config.names_language ?? 'auto'} onValueChange={(v) => save.mutate({ names_language: v === 'auto' ? null : v })}>
          <SelectTrigger className="w-60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">{t('settings.namesAuto', { lang: status?.names_language ?? '' })}</SelectItem>
            {languages.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Section>
      <FacePackFolders />
      <Section title={t('settings.about')}>
        <Facts
          items={[
            [t('settings.app'), `${APP_NAME} ${APP_VERSION}`],
            [
              t('settings.author'),
              <a key="a" href={AUTHOR_GITHUB} target="_blank" rel="noreferrer" className="hover:underline">
                {AUTHOR_NAME}
              </a>,
            ],
            [
              t('settings.code'),
              <a key="c" href={REPO_URL} target="_blank" rel="noreferrer" className="hover:underline">
                {REPO_URL}
              </a>,
            ],
            [t('settings.license'), 'GPL-3.0'],
          ]}
        />
        <p className="mt-4 text-xs text-muted-foreground">{t('settings.disclaimer')}</p>
      </Section>
    </div>
  )
}
