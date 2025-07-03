import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getBehaviorAnalysis, BehaviorAnalysis } from '@/api/lightrag'
import { useAuthStore } from '@/stores/state'
import { useTabVisibility } from '@/contexts/useTabVisibility'

export default function BehaviorAnalysis() {
  const username = useAuthStore.use.username()
  const { t } = useTranslation()
  const { isTabVisible } = useTabVisibility()
  const isVisible = isTabVisible('analysis')

  const [analysis, setAnalysis] = useState<BehaviorAnalysis | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!username || !isVisible) return
    setLoading(true)
    getBehaviorAnalysis(username)
      .then((data) => setAnalysis(data))
      .catch((e) => console.error(e))
      .finally(() => setLoading(false))
  }, [username, isVisible])

  if (!isVisible) return <div className="hidden" />

  return (
    <div className="p-4 space-y-4">
      {loading && <div>{t('behaviorAnalysis.loading')}</div>}
      {analysis && (
        <div className="space-y-2">
          <h2 className="text-lg font-semibold">{t('behaviorAnalysis.title')}</h2>
          <div>
            <h3 className="font-medium">{t('behaviorAnalysis.topWords')}</h3>
            <ul className="list-disc list-inside">
              {analysis.top_words.map(([word, count]) => (
                <li key={word}>{word}: {count}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="font-medium">{t('behaviorAnalysis.topQueries')}</h3>
            <ul className="list-disc list-inside">
              {analysis.top_queries.map(([query, count]) => (
                <li key={query}>{query}: {count}</li>
              ))}
            </ul>
          </div>
          <div>
            {t('behaviorAnalysis.negativeFeedback')}: {analysis.negative_feedback}
          </div>
        </div>
      )}
    </div>
  )
}
