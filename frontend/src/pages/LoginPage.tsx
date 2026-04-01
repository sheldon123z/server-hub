import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'
import { useQueryClient } from '@tanstack/react-query'

/** 登录表单数据 */
interface LoginFormData {
  /** 用户名 */
  username: string
  /** 密码 */
  password: string
}

/**
 * 登录页面
 * 提供 JWT Cookie 认证登录表单，含粒子网络动画背景和鼠标跟随光效
 */
export default function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setUser = useAuthStore((s) => s.setUser)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [mousePos, setMousePos] = useState({ x: -300, y: -300 })
  const [error, setError] = useState('')
  const [isExiting, setIsExiting] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<LoginFormData>()

  const onSubmit = async (data: LoginFormData) => {
    setError('')
    try {
      const res = await authApi.login(data.username, data.password)
      if (res.ok && res.user) {
        setUser(res.user)
        queryClient.clear()
        setIsExiting(true)
        setTimeout(() => navigate('/dashboard', { replace: true }), 350)
      } else {
        setError('登录失败')
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        setError(axiosErr.response?.data?.detail || '登录失败')
      } else {
        setError('网络连接失败，请检查网络')
      }
    }
  }

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    setMousePos({ x: e.clientX, y: e.clientY })
  }, [])

  // Particle network animation
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const COUNT = 40
    const MAX_DIST = 180
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let animId: number
    let w: number, h: number

    interface Particle {
      x: number
      y: number
      vx: number
      vy: number
      r: number
      o: number
    }

    let particles: Particle[] = []

    function init() {
      w = canvas!.width = window.innerWidth
      h = canvas!.height = window.innerHeight
      particles = []
      for (let i = 0; i < COUNT; i++) {
        particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.3,
          vy: (Math.random() - 0.5) * 0.3,
          r: Math.random() * 2 + 2,
          o: Math.random() * 0.4 + 0.15,
        })
      }
    }

    function draw() {
      ctx!.clearRect(0, 0, w, h)

      if (reduced) {
        particles.forEach((p) => {
          ctx!.beginPath()
          ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2)
          ctx!.fillStyle = `rgba(56, 189, 248, ${p.o * 0.4})`
          ctx!.fill()
        })
        return
      }

      particles.forEach((p) => {
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > w) p.vx *= -1
        if (p.y < 0 || p.y > h) p.vy *= -1
      })

      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x
          const dy = particles[i].y - particles[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < MAX_DIST) {
            ctx!.beginPath()
            ctx!.moveTo(particles[i].x, particles[i].y)
            ctx!.lineTo(particles[j].x, particles[j].y)
            ctx!.strokeStyle = `rgba(56, 189, 248, ${(1 - dist / MAX_DIST) * 0.2})`
            ctx!.lineWidth = 0.6
            ctx!.stroke()
          }
        }
        ctx!.beginPath()
        ctx!.arc(particles[i].x, particles[i].y, particles[i].r, 0, Math.PI * 2)
        ctx!.fillStyle = `rgba(56, 189, 248, ${particles[i].o})`
        ctx!.fill()
      }

      animId = requestAnimationFrame(draw)
    }

    const onResize = () => init()
    window.addEventListener('resize', onResize)
    init()
    if (reduced) {
      draw()
    } else {
      animId = requestAnimationFrame(draw)
    }

    return () => {
      window.removeEventListener('resize', onResize)
      cancelAnimationFrame(animId)
    }
  }, [])

  return (
    <div style={styles.root} onMouseMove={handleMouseMove}>
      <style>{keyframesCSS}</style>

      {/* Ambient Glow Orbs */}
      <div style={{ ...styles.glowOrb, ...styles.glowOrb1 }} />
      <div style={{ ...styles.glowOrb, ...styles.glowOrb2 }} />

      {/* SVG Grid Background */}
      <svg style={styles.gridBg} xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
            <path
              d="M 60 0 L 0 0 0 60"
              fill="none"
              stroke="rgba(56,189,248,0.04)"
              strokeWidth="0.5"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>

      {/* Waveform Lines */}
      <div style={styles.waveformContainer}>
        <svg
          viewBox="0 0 1200 200"
          preserveAspectRatio="none"
          style={{ position: 'absolute', width: '120%', left: '-10%', top: '15%', height: 200 }}
        >
          <path
            className="wave-line-1"
            d="M0,100 C150,60 300,140 450,100 C600,60 750,140 900,100 C1050,60 1200,140 1350,100"
            fill="none"
            strokeWidth="1.5"
            strokeLinecap="round"
            stroke="rgba(56, 189, 248, 0.12)"
            strokeDasharray="8 12"
          />
          <path
            className="wave-line-2"
            d="M0,120 C200,80 400,160 600,120 C800,80 1000,160 1200,120"
            fill="none"
            strokeWidth="1.5"
            strokeLinecap="round"
            stroke="rgba(167, 139, 250, 0.08)"
            strokeDasharray="6 16"
          />
        </svg>
        <svg
          viewBox="0 0 1200 200"
          preserveAspectRatio="none"
          style={{ position: 'absolute', width: '120%', left: '-10%', bottom: '20%', height: 180 }}
        >
          <path
            className="wave-line-3"
            d="M0,90 C180,130 360,50 540,90 C720,130 900,50 1080,90 C1260,130 1440,50 1620,90"
            fill="none"
            strokeWidth="1.5"
            strokeLinecap="round"
            stroke="rgba(74, 222, 128, 0.06)"
            strokeDasharray="10 14"
          />
        </svg>
      </div>

      {/* Particle Canvas */}
      <canvas ref={canvasRef} style={styles.canvas} />

      {/* Mouse Follow Glow */}
      <div
        style={{
          ...styles.mouseGlow,
          left: mousePos.x,
          top: mousePos.y,
        }}
      />

      {/* Login Card */}
      <div style={styles.loginContainer}>
        <div
          style={{
            ...styles.loginCard,
            animation: isExiting
              ? 'cardIn 0.4s ease reverse forwards'
              : 'cardIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.2s forwards',
          }}
        >
          {/* Server Icon */}
          <div style={styles.serverIcon}>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ width: 22, height: 22, color: '#38bdf8' }}
            >
              <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
              <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
              <line x1="6" y1="6" x2="6.01" y2="6" />
              <line x1="6" y1="18" x2="6.01" y2="18" />
            </svg>
          </div>

          <h1 style={styles.title}>ServerHub</h1>
          <p style={styles.subtitle}>
            <code style={styles.subtitleCode}>NF5468M6</code> &middot; 服务器管理系统
          </p>

          {/* Error Message */}
          {error && (
            <div style={styles.errorBox}>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={{ width: 16, height: 16, flexShrink: 0, color: '#f87171' }}
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)}>
            <div className="login-input-group" style={styles.inputGroup}>
              <label style={styles.label} htmlFor="username">
                用户名
              </label>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={styles.inputIcon}
              >
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <input
                id="username"
                type="text"
                className="login-form-input"
                style={styles.formInput}
                placeholder="请输入用户名"
                autoComplete="username"
                autoFocus
                {...register('username', { required: true })}
              />
            </div>

            <div className="login-input-group" style={styles.inputGroup}>
              <label style={styles.label} htmlFor="password">
                密码
              </label>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                style={styles.inputIcon}
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
              <input
                id="password"
                type="password"
                className="login-form-input"
                style={styles.formInput}
                placeholder="请输入密码"
                autoComplete="current-password"
                {...register('password', { required: true })}
              />
            </div>

            <button
              type="submit"
              className="login-btn"
              style={styles.btnLogin}
              disabled={isSubmitting}
            >
              <span style={styles.btnContent}>
                {isSubmitting && <span style={styles.spinner} />}
                <span>{isSubmitting ? '验证中...' : '登 录'}</span>
              </span>
            </button>
          </form>

          {/* Footer */}
          <div style={styles.loginFooter}>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              style={{ width: 12, height: 12, opacity: 0.5 }}
            >
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
            HTTPS + JWT Cookie 安全认证
          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div style={styles.bottomBar}>
        <span>ServerHub v1.0</span>
        <div style={styles.techStack}>
          <span style={styles.techItem}>FastAPI</span>
          <span style={styles.techItem}>React</span>
          <span style={styles.techItem}>TypeScript</span>
        </div>
      </div>
    </div>
  )
}

/* ─── Keyframe Animations (injected via <style>) ─── */
const keyframesCSS = `
@keyframes cardIn {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: 0.6; transform: scale(1.05); }
}

@keyframes waveDrift {
  from { stroke-dashoffset: 0; }
  to   { stroke-dashoffset: -200; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes shakeIn {
  0%   { transform: translateX(-8px); opacity: 0; }
  40%  { transform: translateX(4px); }
  70%  { transform: translateX(-2px); }
  100% { transform: translateX(0); opacity: 1; }
}

.wave-line-1 { animation: waveDrift 12s linear infinite; }
.wave-line-2 { animation: waveDrift 16s linear infinite reverse; }
.wave-line-3 { animation: waveDrift 20s linear infinite; }

/* Input focus-within interactions */
.login-input-group:focus-within label {
  color: #38bdf8 !important;
}
.login-input-group:focus-within .login-input-icon {
  color: #38bdf8 !important;
}

/* Form input hover/focus */
.login-form-input:hover {
  border-color: rgba(56, 189, 248, 0.2) !important;
}
.login-form-input:focus {
  border-color: #38bdf8 !important;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.08) !important;
}
.login-form-input::placeholder {
  color: #475569;
  font-size: 13px;
}

/* Button hover effects */
.login-btn {
  position: relative;
  overflow: hidden;
}
.login-btn::before {
  content: '';
  position: absolute;
  top: 0; left: -100%;
  width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.12), transparent);
  transition: left 0.5s ease;
}
.login-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(56, 189, 248, 0.2);
}
.login-btn:hover::before { left: 100%; }
.login-btn:active:not(:disabled) { transform: translateY(0); }

/* Tech stack items */
.login-tech-item { opacity: 0.4; transition: opacity 150ms ease; }
.login-tech-item:hover { opacity: 0.8; }

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* Responsive */
@media (max-width: 768px) {
  .login-wave-container { display: none !important; }
  .login-tech-stack { display: none !important; }
}
`

/* ─── Inline Styles ─── */
const styles: Record<string, React.CSSProperties> = {
  root: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
    background: 'linear-gradient(135deg, #0c1222 0%, #162036 50%, #0f1a2e 100%)',
    color: '#f1f5f9',
    minHeight: '100vh',
    overflow: 'hidden',
    WebkitFontSmoothing: 'antialiased',
    margin: 0,
    padding: 0,
  },

  /* Glow Orbs */
  glowOrb: {
    position: 'fixed',
    borderRadius: '50%',
    pointerEvents: 'none',
    filter: 'blur(80px)',
    zIndex: 0,
  },
  glowOrb1: {
    width: 500,
    height: 500,
    background: 'rgba(56, 189, 248, 0.07)',
    top: '-10%',
    right: '-5%',
    animation: 'breathe 8s ease-in-out infinite',
  },
  glowOrb2: {
    width: 400,
    height: 400,
    background: 'rgba(167, 139, 250, 0.06)',
    bottom: '-10%',
    left: '-5%',
    animation: 'breathe 10s ease-in-out 2s infinite',
  },

  /* Grid Background */
  gridBg: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    zIndex: 0,
    opacity: 0.4,
  },

  /* Waveform Container */
  waveformContainer: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    zIndex: 1,
    pointerEvents: 'none',
    overflow: 'hidden',
  },

  /* Canvas */
  canvas: {
    position: 'fixed',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    zIndex: 2,
  },

  /* Mouse Glow */
  mouseGlow: {
    position: 'fixed',
    width: 500,
    height: 500,
    borderRadius: '50%',
    background: 'radial-gradient(circle, rgba(56, 189, 248, 0.05) 0%, transparent 70%)',
    pointerEvents: 'none',
    zIndex: 3,
    transform: 'translate(-50%, -50%)',
    transition: 'left 0.4s ease-out, top 0.4s ease-out',
  },

  /* Login Container */
  loginContainer: {
    position: 'relative',
    zIndex: 10,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
    padding: 20,
  },

  /* Login Card */
  loginCard: {
    width: 380,
    maxWidth: '92vw',
    background: 'rgba(15, 23, 42, 0.75)',
    backdropFilter: 'blur(20px) saturate(1.2)',
    WebkitBackdropFilter: 'blur(20px) saturate(1.2)',
    border: '1px solid rgba(56, 189, 248, 0.12)',
    borderRadius: 16,
    padding: '36px 32px 32px',
    boxShadow: '0 20px 50px rgba(0, 0, 0, 0.4)',
    opacity: 0,
    transform: 'translateY(16px)',
  },

  /* Server Icon */
  serverIcon: {
    width: 44,
    height: 44,
    margin: '0 auto 16px',
    borderRadius: 12,
    background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(167, 139, 250, 0.08))',
    border: '1px solid rgba(56, 189, 248, 0.15)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },

  /* Title */
  title: {
    textAlign: 'center',
    marginBottom: 4,
    fontSize: 22,
    fontWeight: 700,
    letterSpacing: '-0.3px',
  },
  subtitle: {
    textAlign: 'center',
    color: '#475569',
    fontSize: 13,
    marginBottom: 28,
  },
  subtitleCode: {
    color: '#94a3b8',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: 12,
    background: 'rgba(255,255,255,0.04)',
    padding: '1px 5px',
    borderRadius: 4,
  },

  /* Error */
  errorBox: {
    background: 'rgba(248, 113, 113, 0.08)',
    border: '1px solid rgba(248, 113, 113, 0.2)',
    color: '#fca5a5',
    padding: '10px 14px',
    borderRadius: 8,
    fontSize: 12,
    marginBottom: 14,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    animation: 'shakeIn 0.35s ease',
  },

  /* Form */
  inputGroup: {
    position: 'relative',
    marginBottom: 14,
  },
  label: {
    display: 'block',
    fontSize: 11,
    fontWeight: 500,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.8px',
    color: '#475569',
    marginBottom: 5,
    transition: 'color 150ms ease',
  },
  inputIcon: {
    position: 'absolute',
    left: 12,
    bottom: 11,
    width: 16,
    height: 16,
    color: '#475569',
    pointerEvents: 'none',
    transition: 'color 150ms ease',
  },
  formInput: {
    width: '100%',
    padding: '10px 12px 10px 38px',
    background: 'rgba(15, 23, 42, 0.5)',
    border: '1px solid rgba(51, 65, 85, 0.5)',
    borderRadius: 10,
    color: '#f1f5f9',
    fontSize: 14,
    fontFamily: 'inherit',
    outline: 'none',
    transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
  },

  /* Button */
  btnLogin: {
    width: '100%',
    padding: '11px 24px',
    marginTop: 6,
    background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.85), rgba(99, 155, 255, 0.85))',
    border: 'none',
    borderRadius: 10,
    color: '#0f172a',
    fontSize: 14,
    fontWeight: 600,
    fontFamily: 'inherit',
    cursor: 'pointer',
    transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
  btnContent: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    position: 'relative',
    zIndex: 1,
  },
  spinner: {
    display: 'inline-block',
    width: 16,
    height: 16,
    border: '2px solid rgba(15, 23, 42, 0.3)',
    borderTopColor: '#0f172a',
    borderRadius: '50%',
    animation: 'spin 0.6s linear infinite',
  },

  /* Footer */
  loginFooter: {
    textAlign: 'center',
    marginTop: 20,
    paddingTop: 16,
    borderTop: '1px solid rgba(51, 65, 85, 0.25)',
    fontSize: 11,
    color: '#475569',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },

  /* Bottom Bar */
  bottomBar: {
    position: 'fixed',
    bottom: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    padding: '12px 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: 11,
    color: '#475569',
    background: 'linear-gradient(to top, rgba(12, 18, 34, 0.7), transparent)',
    animation: 'fadeUp 0.4s ease 1s both',
  },
  techStack: {
    display: 'flex',
    gap: 16,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    fontSize: 10,
  },
  techItem: {
    opacity: 0.4,
    transition: 'opacity 150ms ease',
    cursor: 'default',
  },
}
