import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { createSelectors } from '@/lib/utils'
import { defaultQueryLabel } from '@/lib/constants'
import { Message, QueryRequest } from '@/api/lightrag'

const generateConversationId = (): string =>
  `conv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

const initialConversationId = generateConversationId()

type Theme = 'dark' | 'light' | 'system'
type Language = 'en' | 'zh' | 'fr' | 'ar' | 'zh_TW'
type Tab = 'documents' | 'knowledge-graph' | 'retrieval' | 'api' | 'accounts'

interface SettingsState {
  // Document manager settings
  showFileName: boolean
  setShowFileName: (show: boolean) => void

  // Graph viewer settings
  showPropertyPanel: boolean
  showNodeSearchBar: boolean
  showLegend: boolean
  setShowLegend: (show: boolean) => void

  showNodeLabel: boolean
  enableNodeDrag: boolean

  showEdgeLabel: boolean
  enableHideUnselectedEdges: boolean
  enableEdgeEvents: boolean

  minEdgeSize: number
  setMinEdgeSize: (size: number) => void

  maxEdgeSize: number
  setMaxEdgeSize: (size: number) => void

  graphQueryMaxDepth: number
  setGraphQueryMaxDepth: (depth: number) => void

  graphMaxNodes: number
  setGraphMaxNodes: (nodes: number) => void

  graphLayoutMaxIterations: number
  setGraphLayoutMaxIterations: (iterations: number) => void

  // Retrieval settings
  queryLabel: string
  setQueryLabel: (queryLabel: string) => void

  retrievalHistory: Message[]
  setRetrievalHistory: (history: Message[]) => void

  conversations: Record<string, Message[]>
  createConversation: () => string
  deleteConversation: (id: string) => void

  querySettings: Omit<QueryRequest, 'query' | 'conversation_history' | 'user_profile' | 'conversation_id' | 'user_id'>
  updateQuerySettings: (settings: Partial<QueryRequest>) => void

  conversationId: string
  setConversationId: (id: string) => void

  userProfile: Record<string, any>
  updateUserProfile: (profile: Record<string, any>) => void

  // Auth settings
  apiKey: string | null
  setApiKey: (key: string | null) => void

  // App settings
  theme: Theme
  setTheme: (theme: Theme) => void

  language: Language
  setLanguage: (lang: Language) => void

  enableHealthCheck: boolean
  setEnableHealthCheck: (enable: boolean) => void

  currentTab: Tab
  setCurrentTab: (tab: Tab) => void
}

const useSettingsStoreBase = create<SettingsState>()(
  persist(
    (set) => ({
      theme: 'system',
      language: 'en',
      showPropertyPanel: true,
      showNodeSearchBar: true,
      showLegend: false,

      showNodeLabel: true,
      enableNodeDrag: true,

      showEdgeLabel: false,
      enableHideUnselectedEdges: true,
      enableEdgeEvents: false,

      minEdgeSize: 1,
      maxEdgeSize: 1,

      graphQueryMaxDepth: 3,
      graphMaxNodes: 1000,
      graphLayoutMaxIterations: 15,

      queryLabel: defaultQueryLabel,

      enableHealthCheck: true,

      apiKey: null,

      currentTab: 'documents',
      showFileName: false,

      retrievalHistory: [],

      conversationId: initialConversationId,
      conversations: { [initialConversationId]: [] },
      userProfile: {},

      querySettings: {
        mode: 'global',
        response_type: 'Multiple Paragraphs',
        top_k: 10,
        max_token_for_text_unit: 4000,
        max_token_for_global_context: 4000,
        max_token_for_local_context: 4000,
        only_need_context: false,
        only_need_prompt: false,
        stream: true,
        history_turns: 3,
        hl_keywords: [],
        ll_keywords: [],
        user_prompt: ''
      },

      setTheme: (theme: Theme) => set({ theme }),

      setLanguage: (language: Language) => {
        set({ language })
        // Update i18n after state is updated
        import('i18next').then(({ default: i18n }) => {
          if (i18n.language !== language) {
            i18n.changeLanguage(language)
          }
        })
      },

      setGraphLayoutMaxIterations: (iterations: number) =>
        set({
          graphLayoutMaxIterations: iterations
        }),

      setQueryLabel: (queryLabel: string) =>
        set({
          queryLabel
        }),

      setGraphQueryMaxDepth: (depth: number) => set({ graphQueryMaxDepth: depth }),

      setGraphMaxNodes: (nodes: number) => set({ graphMaxNodes: nodes }),

      setMinEdgeSize: (size: number) => set({ minEdgeSize: size }),

      setMaxEdgeSize: (size: number) => set({ maxEdgeSize: size }),

      setEnableHealthCheck: (enable: boolean) => set({ enableHealthCheck: enable }),

      setApiKey: (apiKey: string | null) => set({ apiKey }),

      setCurrentTab: (tab: Tab) => set({ currentTab: tab }),

      setRetrievalHistory: (history: Message[]) =>
        set((state) => ({
          retrievalHistory: history,
          conversations: {
            ...state.conversations,
            [state.conversationId]: history,
          },
        })),

      updateQuerySettings: (settings: Partial<QueryRequest>) =>
        set((state) => ({
          querySettings: { ...state.querySettings, ...settings }
        })),

      setConversationId: (id: string) =>
        set((state) => ({
          conversationId: id,
          retrievalHistory: state.conversations[id] || [],
        })),

      createConversation: () => {
        const id = generateConversationId()
        set((state) => ({
          conversationId: id,
          retrievalHistory: [],
          conversations: { ...state.conversations, [id]: [] },
        }))
        return id
      },

      deleteConversation: (id: string) =>
        set((state) => {
          const convs = { ...state.conversations }
          delete convs[id]
          let newId = state.conversationId
          let history = state.retrievalHistory
          if (state.conversationId === id) {
            const ids = Object.keys(convs)
            if (ids.length > 0) {
              newId = ids[0]
              history = convs[newId]
            } else {
              newId = generateConversationId()
              convs[newId] = []
              history = []
            }
          }
          return {
            conversations: convs,
            conversationId: newId,
            retrievalHistory: history,
          }
        }),

      updateUserProfile: (profile: Record<string, any>) =>
        set((state) => ({ userProfile: { ...state.userProfile, ...profile } })),

      setShowFileName: (show: boolean) => set({ showFileName: show }),
      setShowLegend: (show: boolean) => set({ showLegend: show })
    }),
    {
      name: 'settings-storage',
      storage: createJSONStorage(() => localStorage),
      version: 15,
      migrate: (state: any, version: number) => {
        if (version < 2) {
          state.showEdgeLabel = false
        }
        if (version < 3) {
          state.queryLabel = defaultQueryLabel
        }
        if (version < 4) {
          state.showPropertyPanel = true
          state.showNodeSearchBar = true
          state.showNodeLabel = true
          state.enableHealthCheck = true
          state.apiKey = null
        }
        if (version < 5) {
          state.currentTab = 'documents'
        }
        if (version < 6) {
          state.querySettings = {
            mode: 'global',
            response_type: 'Multiple Paragraphs',
            top_k: 10,
            max_token_for_text_unit: 4000,
            max_token_for_global_context: 4000,
            max_token_for_local_context: 4000,
            only_need_context: false,
            only_need_prompt: false,
            stream: true,
            history_turns: 3,
            hl_keywords: [],
            ll_keywords: []
          }
          state.retrievalHistory = []
        }
        if (version < 7) {
          state.graphQueryMaxDepth = 3
          state.graphLayoutMaxIterations = 15
        }
        if (version < 8) {
          state.graphMinDegree = 0
          state.language = 'en'
        }
        if (version < 9) {
          state.showFileName = false
        }
        if (version < 10) {
          delete state.graphMinDegree // 删除废弃参数
          state.graphMaxNodes = 1000  // 添加新参数
        }
        if (version < 11) {
          state.minEdgeSize = 1
          state.maxEdgeSize = 1
        }
        if (version < 12) {
          // Clear retrieval history to avoid compatibility issues with MessageWithError type
          state.retrievalHistory = []
        }
        if (version < 13) {
          // Add user_prompt field for older versions
          if (state.querySettings) {
            state.querySettings.user_prompt = ''
          }
        }
        if (version < 14) {
          state.conversationId = generateConversationId()
          state.userProfile = {}
        }
        if (version < 15) {
          const convId = state.conversationId || generateConversationId()
          state.conversations = { [convId]: state.retrievalHistory || [] }
        }
        return state
      }
    }
  )
)

const useSettingsStore = createSelectors(useSettingsStoreBase)

export { useSettingsStore, type Theme }
