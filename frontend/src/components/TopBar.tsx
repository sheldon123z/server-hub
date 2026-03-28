import { useAuthStore } from '@/stores/authStore'
import { authApi } from '@/api/auth'
import { useNavigate } from 'react-router-dom'

interface TopBarProps {
  title: string
}

export default function TopBar({ title }: TopBarProps) {
  const { user, setUser } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await authApi.logout()
    setUser(null)
    navigate('/login')
  }

  return (
    <header className="h-header border-b border-border flex items-center justify-between px-6 flex-shrink-0">
      <div className="text-base font-semibold">{title}</div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-text3">每 15s 自动刷新</span>
        {user && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-text2">{user.display_name || user.username}</span>
            <span className="text-[10px] text-text3">{user.role}</span>
            <button
              onClick={handleLogout}
              className="text-xs px-2 py-1 rounded border border-border text-text2 hover:text-text hover:border-border-light transition-colors"
            >
              退出
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
