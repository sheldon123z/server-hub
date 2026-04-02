/**
 * ConfigForm — interactive configuration form for agent messages.
 * Supports text, number, select, switch, textarea, and password fields
 * with basic validation and action buttons.
 */

import { useState, useCallback } from 'react'
import { RotateCcw } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FormField {
  name: string
  label: string
  type: 'text' | 'number' | 'select' | 'switch' | 'textarea' | 'password'
  placeholder?: string
  validation?: { required?: boolean; min?: number; max?: number; pattern?: string }
  options?: Array<{ label: string; value: string }>
  disabled?: boolean
}

interface FormAction {
  id: string
  label: string
  variant?: 'primary' | 'secondary' | 'danger'
  action_type: 'submit' | 'reset' | 'agent'
}

interface FormComponent {
  id: string
  type: 'form'
  title?: string
  fields: FormField[]
  initialValues?: Record<string, unknown>
  actions?: FormAction[]
}

interface ConfigFormProps {
  component: FormComponent
  onAction: (actionId: string, payload?: Record<string, unknown>) => void
  loadingActions?: Set<string>
}

/* ── Variant styles ─────────────────────────────── */

const VARIANT_STYLES: Record<string, string> = {
  primary: 'bg-accent text-[#0f172a] hover:opacity-90',
  secondary: 'bg-bg3 text-text2 hover:text-text border border-border',
  danger: 'bg-red/20 text-red border border-red/30 hover:bg-red/30',
}

/* ── Component ─────────────────────────────────── */

export function ConfigForm({ component, onAction, loadingActions }: ConfigFormProps) {
  const { title, fields, initialValues, actions } = component

  const [values, setValues] = useState<Record<string, unknown>>(() => {
    const init: Record<string, unknown> = {}
    for (const f of fields) {
      init[f.name] = initialValues?.[f.name] ?? (f.type === 'switch' ? false : f.type === 'number' ? '' : '')
    }
    return init
  })

  const [errors, setErrors] = useState<Record<string, string>>({})

  /* Field value setter */
  const setValue = useCallback((name: string, value: unknown) => {
    setValues((prev) => ({ ...prev, [name]: value }))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[name]
      return next
    })
  }, [])

  /* Validation */
  const validate = useCallback((): boolean => {
    const newErrors: Record<string, string> = {}
    for (const f of fields) {
      const val = values[f.name]
      if (f.validation?.required) {
        if (val === '' || val === undefined || val === null) {
          newErrors[f.name] = `${f.label}为必填项`
          continue
        }
      }
      if (f.type === 'number' && val !== '' && val !== undefined) {
        const num = Number(val)
        if (f.validation?.min !== undefined && num < f.validation.min) {
          newErrors[f.name] = `最小值为 ${f.validation.min}`
        }
        if (f.validation?.max !== undefined && num > f.validation.max) {
          newErrors[f.name] = `最大值为 ${f.validation.max}`
        }
      }
      if (f.validation?.pattern && typeof val === 'string' && val) {
        try {
          if (!new RegExp(f.validation.pattern).test(val)) {
            newErrors[f.name] = `格式不正确`
          }
        } catch { /* invalid regex, skip */ }
      }
    }
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }, [fields, values])

  /* Action handler */
  const handleAction = useCallback((action: FormAction) => {
    if (action.action_type === 'reset') {
      const init: Record<string, unknown> = {}
      for (const f of fields) {
        init[f.name] = initialValues?.[f.name] ?? (f.type === 'switch' ? false : f.type === 'number' ? '' : '')
      }
      setValues(init)
      setErrors({})
      return
    }

    // submit or agent: validate then callback
    if (!validate()) return
    onAction(action.id, { ...values })
  }, [fields, initialValues, values, validate, onAction])

  return (
    <div className="border border-border bg-card rounded-lg p-4">
      {title && (
        <div className="text-sm font-medium text-text mb-3">{title}</div>
      )}

      <div className="space-y-3">
        {fields.map((field) => (
          <div key={field.name}>
            {/* Label */}
            <label className="block text-xs font-medium text-text2 mb-1">
              {field.label}
              {field.validation?.required && <span className="text-red ml-0.5">*</span>}
            </label>

            {/* Input controls */}
            {field.type === 'switch' ? (
              <button
                type="button"
                role="switch"
                aria-checked={!!values[field.name]}
                disabled={field.disabled}
                onClick={() => setValue(field.name, !values[field.name])}
                className={cn(
                  'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
                  values[field.name] ? 'bg-accent' : 'bg-bg3',
                  field.disabled && 'opacity-50 cursor-not-allowed',
                )}
              >
                <span
                  className={cn(
                    'inline-block h-4 w-4 rounded-full bg-white transition-transform',
                    values[field.name] ? 'translate-x-4' : 'translate-x-0.5',
                  )}
                />
              </button>
            ) : field.type === 'select' ? (
              <select
                value={String(values[field.name] ?? '')}
                disabled={field.disabled}
                onChange={(e) => setValue(field.name, e.target.value)}
                className={cn(
                  'w-full rounded border border-border bg-bg text-text text-sm px-2 py-1.5',
                  'focus:outline-none focus:border-accent',
                  field.disabled && 'opacity-50 cursor-not-allowed',
                )}
              >
                <option value="">请选择...</option>
                {field.options?.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            ) : field.type === 'textarea' ? (
              <textarea
                value={String(values[field.name] ?? '')}
                placeholder={field.placeholder}
                disabled={field.disabled}
                rows={3}
                onChange={(e) => setValue(field.name, e.target.value)}
                className={cn(
                  'w-full rounded border border-border bg-bg text-text text-sm px-2 py-1.5',
                  'focus:outline-none focus:border-accent resize-y',
                  field.disabled && 'opacity-50 cursor-not-allowed',
                )}
              />
            ) : (
              <input
                type={field.type === 'password' ? 'password' : field.type === 'number' ? 'number' : 'text'}
                value={String(values[field.name] ?? '')}
                placeholder={field.placeholder}
                disabled={field.disabled}
                min={field.validation?.min}
                max={field.validation?.max}
                onChange={(e) => setValue(
                  field.name,
                  field.type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value,
                )}
                className={cn(
                  'w-full rounded border border-border bg-bg text-text text-sm px-2 py-1.5',
                  'focus:outline-none focus:border-accent',
                  field.disabled && 'opacity-50 cursor-not-allowed',
                )}
              />
            )}

            {/* Error message */}
            {errors[field.name] && (
              <p className="text-red text-xs mt-0.5">{errors[field.name]}</p>
            )}
          </div>
        ))}
      </div>

      {/* Action buttons */}
      {actions && actions.length > 0 && (
        <div className="flex items-center gap-2 mt-4 pt-3 border-t border-border">
          {actions.map((action) => {
            const isLoading = loadingActions?.has(action.id)
            const variant = action.variant ?? 'primary'

            return (
              <button
                key={action.id}
                onClick={() => handleAction(action)}
                disabled={isLoading}
                className={cn(
                  'px-3 py-1.5 rounded text-xs font-medium transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  VARIANT_STYLES[variant],
                )}
              >
                {action.action_type === 'reset' && <RotateCcw className="w-3 h-3 mr-1 inline" />}
                {isLoading ? '处理中...' : action.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
