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

export interface GrepResult {
  file: string
  line_no: number
  content: string
}

export interface GrepResponse {
  path: string
  pattern: string
  results: GrepResult[]
  total: number
}

export interface FileStat {
  path: string
  name: string
  size: number
  permissions: string
  octal_permissions: string
  owner: string
  group: string
  mtime: number
  ctime: number
  is_dir: boolean
  is_symlink: boolean
  symlink_target: string | null
}
