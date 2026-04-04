import React from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ArtifactCard } from '@/pages/agents/ArtifactCard'
import { useArtifactStore } from '@/stores/artifactStore'

// ---------------------------------------------------------------------------
// Mock lucide-react to avoid SVG rendering complexity in jsdom
// ---------------------------------------------------------------------------
vi.mock('lucide-react', () => ({
  FileText: () => null,
}))

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('ArtifactCard', () => {
  beforeEach(() => {
    useArtifactStore.getState().clear()
  })

  it('renders file name extracted from full path', () => {
    render(<ArtifactCard filePath="/home/user/project/main.py" action="write_file" />)
    expect(screen.getByText('main.py')).toBeInTheDocument()
  })

  it('renders bare file name when path has no slashes', () => {
    render(<ArtifactCard filePath="server.ts" action="edit_file" />)
    expect(screen.getByText('server.ts')).toBeInTheDocument()
  })

  it('shows 新建 badge for write_file action', () => {
    render(<ArtifactCard filePath="/app.py" action="write_file" />)
    expect(screen.getByText('新建')).toBeInTheDocument()
  })

  it('shows 编辑 badge for edit_file action', () => {
    render(<ArtifactCard filePath="/app.py" action="edit_file" />)
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  it('does not show 编辑 badge when action is write_file', () => {
    render(<ArtifactCard filePath="/app.py" action="write_file" />)
    expect(screen.queryByText('编辑')).not.toBeInTheDocument()
  })

  it('does not show 新建 badge when action is edit_file', () => {
    render(<ArtifactCard filePath="/app.py" action="edit_file" />)
    expect(screen.queryByText('新建')).not.toBeInTheDocument()
  })

  it('shows full path as title tooltip', () => {
    const fullPath = '/home/user/project/components/Button.tsx'
    render(<ArtifactCard filePath={fullPath} action="write_file" />)
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('title', fullPath)
  })

  it('click calls artifactStore.select with the correct file path', () => {
    const filePath = '/srv/api/routes.py'
    const selectSpy = vi.spyOn(useArtifactStore.getState(), 'select')

    render(<ArtifactCard filePath={filePath} action="edit_file" />)
    fireEvent.click(screen.getByRole('button'))

    // select is called via getState() inside the component — verify store state instead
    expect(useArtifactStore.getState().selectedPath).toBe(filePath)
    expect(useArtifactStore.getState().isOpen).toBe(true)

    selectSpy.mockRestore()
  })

  it('renders as a button element', () => {
    render(<ArtifactCard filePath="/x.py" action="write_file" />)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })
})
