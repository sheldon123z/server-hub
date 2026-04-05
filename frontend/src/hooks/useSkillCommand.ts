/**
 * useSkillCommand - Hook for detecting and handling /skill: prefix in chat input.
 * Fetches enabled skills, provides fuzzy search, and manages selection state.
 */

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listEnabledSkills, type SkillListItem } from '@/api/skills'

interface UseSkillCommandReturn {
  /** Whether the current input starts with /skill: */
  isSkillCommand: boolean
  /** Skills matching the current query after /skill: */
  filteredSkills: SkillListItem[]
  /** Currently highlighted/selected skill (before confirm) */
  selectedSkill: SkillListItem | null
  /** Confirm selection of a skill */
  selectSkill: (skill: SkillListItem) => void
  /** Clear skill command state (e.g. on send or escape) */
  clearSkillCommand: () => void
  /** The chosen skill_id to attach to the message, or null */
  activeSkillId: string | null
}

/**
 * Detect `/skill:` prefix in the input text, fetch enabled skills,
 * and provide fuzzy-filtered results for the command menu.
 */
export function useSkillCommand(inputText: string): UseSkillCommandReturn {
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null)

  const isSkillCommand = inputText.startsWith('/skill:')

  const { data: skills = [] } = useQuery({
    queryKey: ['enabled-skills'],
    queryFn: () => listEnabledSkills(),
    staleTime: 30_000,
    enabled: isSkillCommand,
  })

  const query = useMemo(() => {
    if (!isSkillCommand) return ''
    return inputText.slice('/skill:'.length).toLowerCase().trim()
  }, [inputText, isSkillCommand])

  const filteredSkills = useMemo(() => {
    if (!isSkillCommand) return []
    if (!query) return skills
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(query) ||
        s.description.toLowerCase().includes(query),
    )
  }, [skills, query, isSkillCommand])

  const selectedSkill = useMemo(() => {
    if (!activeSkillId) return null
    return skills.find((s) => s.id === activeSkillId) ?? null
  }, [activeSkillId, skills])

  const selectSkill = useCallback((skill: SkillListItem) => {
    setActiveSkillId(skill.id)
  }, [])

  const clearSkillCommand = useCallback(() => {
    setActiveSkillId(null)
  }, [])

  // Clear active skill if input is no longer a skill command
  useEffect(() => {
    if (!isSkillCommand) {
      setActiveSkillId(null)
    }
  }, [isSkillCommand])

  return {
    isSkillCommand,
    filteredSkills,
    selectedSkill,
    selectSkill,
    clearSkillCommand,
    activeSkillId,
  }
}
