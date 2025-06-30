import { useTranslation } from 'react-i18next'
import Button from '@/components/ui/Button'
import { useSettingsStore } from '@/stores/settings'
import type { Message } from '@/api/lightrag'

const ConversationSidebar = () => {
  const { t } = useTranslation()
  const conversations = useSettingsStore((s) => s.conversations)
  const conversationId = useSettingsStore((s) => s.conversationId)
  const setConversationId = useSettingsStore((s) => s.setConversationId)
  const createConversation = useSettingsStore((s) => s.createConversation)
  const deleteConversation = useSettingsStore((s) => s.deleteConversation)

  const renderTitle = (msgs: Message[], idx: number) => {
    const first = msgs.find((m) => m.role === 'user')
    if (first) return first.content.slice(0, 20)
    return t('conversationSidebar.untitled', { index: idx })
  }

  return (
    <div className="flex flex-col w-48 gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">
          {t('conversationSidebar.title')}
        </h2>
        <Button variant="outline" size="sm" onClick={() => createConversation()}>
          {t('conversationSidebar.new')}
        </Button>
      </div>
      <div className="flex flex-col gap-1 overflow-auto">
        {Object.entries(conversations).map(([id, msgs], idx) => (
          <div
            key={id}
            className={`cursor-pointer border rounded px-2 py-1 ${
              id === conversationId ? 'bg-primary/10' : ''
            }`}
            onClick={() => setConversationId(id)}
          >
            <div className="flex items-center justify-between">
              <span className="truncate text-sm">
                {renderTitle(msgs, idx + 1)}
              </span>
              <Button
                variant="ghost"
                size="icon"
                onClick={(e) => {
                  e.stopPropagation()
                  deleteConversation(id)
                }}
              >
                ×
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ConversationSidebar
