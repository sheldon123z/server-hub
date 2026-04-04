import { describe, it, expect } from 'vitest'

/**
 * Tests for the FILE_PATH_RE regex used in MarkdownContent FilePathChip.
 * Imported regex pattern duplicated here to test in isolation.
 */
const FILE_PATH_RE =
  /(\/(?:tmp\/serverhub-sandbox|home|var\/log|etc|opt|mnt)\/[\w.\-/]+(?:\.\w{1,10})?)/g

function findPaths(text: string): string[] {
  return [...text.matchAll(FILE_PATH_RE)].map((m) => m[0])
}

describe('FILE_PATH_RE', () => {
  it('detects sandbox paths', () => {
    const text = '文件已保存到 /tmp/serverhub-sandbox/output/chart.svg'
    expect(findPaths(text)).toEqual(['/tmp/serverhub-sandbox/output/chart.svg'])
  })

  it('detects home directory paths', () => {
    const text = '配置文件位于 /home/zhengxiaodong/scripts/config.yaml'
    expect(findPaths(text)).toEqual(['/home/zhengxiaodong/scripts/config.yaml'])
  })

  it('detects log paths', () => {
    const text = '查看日志 /var/log/nginx/access.log'
    expect(findPaths(text)).toEqual(['/var/log/nginx/access.log'])
  })

  it('detects etc paths', () => {
    const text = '修改 /etc/nginx/sites-enabled/default 后重启'
    expect(findPaths(text)).toEqual(['/etc/nginx/sites-enabled/default'])
  })

  it('detects multiple paths in one string', () => {
    const text = '比较 /tmp/serverhub-sandbox/a.py 和 /home/user/b.py'
    expect(findPaths(text)).toEqual([
      '/tmp/serverhub-sandbox/a.py',
      '/home/user/b.py',
    ])
  })

  it('does not match unrelated paths', () => {
    const text = '访问 /api/agents/chat 接口'
    expect(findPaths(text)).toEqual([])
  })

  it('does not match partial prefixes', () => {
    const text = '目录 /tmp/other-dir/file.txt 不在沙箱中'
    expect(findPaths(text)).toEqual([])
  })

  it('handles paths with dots and hyphens', () => {
    const text = '/tmp/serverhub-sandbox/my-project/src/utils.test.ts'
    expect(findPaths(text)).toEqual(['/tmp/serverhub-sandbox/my-project/src/utils.test.ts'])
  })

  it('handles paths without extension', () => {
    const text = '查看 /var/log/syslog 文件'
    expect(findPaths(text)).toEqual(['/var/log/syslog'])
  })
})
