export interface ApiOkResponse {
  ok: boolean
  message?: string
  [key: string]: unknown
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
}

export interface SidebarItem {
  name: string
  display_name: string
  icon: string
  category: string
  required_role: string
  order: number
}
