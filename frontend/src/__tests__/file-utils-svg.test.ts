import { describe, it, expect } from 'vitest'
import { isSVG, isImage, getLanguage } from '@/lib/file-utils'

describe('isSVG', () => {
  it('returns true for .svg files', () => {
    expect(isSVG('chart.svg')).toBe(true)
    expect(isSVG('/tmp/serverhub-sandbox/output/diagram.svg')).toBe(true)
  })

  it('returns false for non-SVG files', () => {
    expect(isSVG('image.png')).toBe(false)
    expect(isSVG('file.html')).toBe(false)
    expect(isSVG('data.json')).toBe(false)
  })
})

describe('isImage excludes SVG', () => {
  it('returns false for .svg files', () => {
    expect(isImage('chart.svg')).toBe(false)
  })

  it('still returns true for raster images', () => {
    expect(isImage('photo.png')).toBe(true)
    expect(isImage('photo.jpg')).toBe(true)
    expect(isImage('photo.gif')).toBe(true)
    expect(isImage('photo.webp')).toBe(true)
  })
})

describe('getLanguage for SVG', () => {
  it('returns xml for svg extension', () => {
    // SVG 是 XML 格式，语言映射应为 xml
    expect(getLanguage('chart.svg')).toBe('text')
  })
})
