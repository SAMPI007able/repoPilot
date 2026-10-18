import type { SupportCategory, SupportTicketStatus } from '../types/api'

export const supportEmail = 'repopilotapp@gmail.com'
export const supportMailto = `mailto:${supportEmail}?subject=${encodeURIComponent('RepoPilot support')}`

export const supportCategoryOptions: { value: SupportCategory; label: string }[] = [
  { value: 'CHAT_WITH_CODEBASE', label: 'Chat with Codebase' },
  { value: 'TEST_GENERATION', label: 'Test Generation' },
  { value: 'IMPACT_ANALYSIS', label: 'Impact Analysis' },
  { value: 'PREVIEW', label: 'Preview' },
  { value: 'OTHER', label: 'Other' },
]

export const supportCategoryLabels = Object.fromEntries(
  supportCategoryOptions.map((option) => [option.value, option.label]),
) as Record<SupportCategory, string>

export const supportStatusLabels: Record<SupportTicketStatus, string> = {
  OPEN: 'Open',
  IN_PROGRESS: 'In Progress',
  COMPLETED: 'Completed',
}
