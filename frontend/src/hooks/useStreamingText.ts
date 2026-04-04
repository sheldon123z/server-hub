/**
 * useStreamingText — 逐字符/逐词流式显示动画
 *
 * streaming 期间逐字展示文本，支持中文词分割（使用 Intl.Segmenter）
 * 完成后返回完整文本
 */

import { useState, useEffect, useRef } from 'react'

interface UseStreamingTextOptions {
  /** 每个 segment 的延迟(ms)，默认 12 */
  segmentDelay?: number
  /** 是否启用动画（false 则直接显示全文） */
  enabled?: boolean
}

// 中文分词器（浏览器原生 API，无需依赖）
const segmenter =
  typeof Intl !== 'undefined' && 'Segmenter' in Intl
    ? new Intl.Segmenter('zh', { granularity: 'word' })
    : null

/** 将文本分割为显示单元（中文按词，其他按字符） */
function segmentText(text: string): string[] {
  if (!segmenter) {
    // fallback: 逐字符
    return [...text]
  }
  return [...segmenter.segment(text)].map((s) => s.segment)
}

export function useStreamingText(
  fullContent: string,
  options: UseStreamingTextOptions = {},
) {
  const { segmentDelay = 12, enabled = true } = options
  const [displayedLength, setDisplayedLength] = useState(0)
  const segmentsRef = useRef<string[]>([])
  const segmentIndexRef = useRef(0)
  const rafRef = useRef<number>(0)
  const lastTimeRef = useRef(0)
  const prevContentRef = useRef('')
  const [restartKey, setRestartKey] = useState(0)

  // 当 fullContent 变化时，更新 segments 并触发动画重启
  useEffect(() => {
    if (!enabled) return

    // 只处理新增的部分
    if (fullContent.startsWith(prevContentRef.current)) {
      const newPart = fullContent.slice(prevContentRef.current.length)
      if (newPart) {
        segmentsRef.current.push(...segmentText(newPart))
        setRestartKey((k) => k + 1) // 唤醒 RAF 循环
      }
    } else {
      // 内容完全变化，重置
      segmentsRef.current = segmentText(fullContent)
      segmentIndexRef.current = 0
      setDisplayedLength(0)
      setRestartKey((k) => k + 1)
    }
    prevContentRef.current = fullContent
  }, [fullContent, enabled])

  // 动画循环 — 仅依赖 restartKey 触发，不依赖 fullContent
  useEffect(() => {
    if (!enabled) {
      setDisplayedLength(fullContent.length)
      return
    }

    function animate(time: number) {
      if (time - lastTimeRef.current >= segmentDelay) {
        lastTimeRef.current = time
        if (segmentIndexRef.current < segmentsRef.current.length) {
          segmentIndexRef.current++
          const shown = segmentsRef.current
            .slice(0, segmentIndexRef.current)
            .join('').length
          setDisplayedLength(shown)
        }
      }
      if (segmentIndexRef.current < segmentsRef.current.length) {
        rafRef.current = requestAnimationFrame(animate)
      }
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, segmentDelay, restartKey])

  const displayedContent = enabled
    ? fullContent.slice(0, displayedLength)
    : fullContent

  const isAnimating = enabled && displayedLength < fullContent.length

  return { displayedContent, isAnimating }
}
