import React from 'react'
import { useGraphStore } from '@/stores/graph'
import Button from '@/components/ui/Button'
import { useTranslation } from 'react-i18next'

const MultiSelectActions = () => {
  const { t } = useTranslation()
  const selected = useGraphStore.use.multiSelectedNodes()

  if (!selected || selected.length <= 1) return null

  const handleMerge = () => {
    console.log('merge nodes', selected)
    // Placeholder for merge_entities API call
  }

  const handleCreateRelation = () => {
    console.log('create relation', selected)
    // Placeholder for create_relation API call
  }

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2 bg-background/80 p-2 rounded-lg border">
      <Button size="sm" onClick={handleMerge}>{t('graphPanel.multiSelect.merge')}</Button>
      <Button size="sm" onClick={handleCreateRelation}>{t('graphPanel.multiSelect.createRelation')}</Button>
    </div>
  )
}

export default MultiSelectActions
