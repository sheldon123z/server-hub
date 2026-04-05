/**
 * 文件管理器共享类型定义
 */

export interface FileEntry {
  name: string
  path: string
  type: 'file' | 'directory'
  size: number
  mtime: string
  permissions?: string
}

export interface FileListResponse {
  path: string
  entries: FileEntry[]
  total_files: number
  total_dirs: number
}

export interface ReadResponse {
  path: string
  content: string
  size: number
  encoding?: string
}

export interface SearchResult {
  name: string
  path: string
  type: 'file' | 'directory'
  size: number
  mtime: string
}

export interface SearchResponse {
  path: string
  query: string
  results: SearchResult[]
  total: number
}
