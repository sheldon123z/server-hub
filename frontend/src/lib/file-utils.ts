/**
 * file-utils — 文件类型检测与语言映射，共享于 FileViewDialog 和 ArtifactsPanel。
 */

export const LANGUAGE_MAP: Record<string, string> = {
  js: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  py: 'python',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  java: 'java',
  cpp: 'cpp',
  c: 'c',
  cs: 'csharp',
  php: 'php',
  swift: 'swift',
  kt: 'kotlin',
  scala: 'scala',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  json: 'json',
  xml: 'xml',
  html: 'html',
  css: 'css',
  scss: 'scss',
  sass: 'sass',
  less: 'less',
  sql: 'sql',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'toml',
  ini: 'ini',
  dockerfile: 'dockerfile',
  makefile: 'makefile',
  conf: 'ini',
  cfg: 'ini',
  log: 'text',
  txt: 'text',
  env: 'bash',
  service: 'ini',
  timer: 'ini',
  nginx: 'nginx',
}

export function getLanguage(fileName: string): string {
  const lower = fileName.toLowerCase()
  const basename = lower.split('/').pop() ?? lower
  if (basename === 'dockerfile') return 'dockerfile'
  if (basename === 'makefile') return 'makefile'
  const ext = basename.split('.').pop() ?? ''
  return LANGUAGE_MAP[ext] ?? 'text'
}

export function getFileExtension(fileName: string): string {
  return (fileName.toLowerCase().split('.').pop() ?? '').toLowerCase()
}

export function isMarkdown(fileName: string): boolean {
  const ext = getFileExtension(fileName)
  return ext === 'md' || ext === 'mdx'
}

export function isSVG(fileName: string): boolean {
  return getFileExtension(fileName) === 'svg'
}

export function isImage(fileName: string): boolean {
  const ext = getFileExtension(fileName)
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico'].includes(ext)
}

export function isHTML(fileName: string): boolean {
  const ext = getFileExtension(fileName)
  return ext === 'html' || ext === 'htm'
}

export function getFileName(filePath: string): string {
  return filePath.split('/').pop() ?? filePath
}
