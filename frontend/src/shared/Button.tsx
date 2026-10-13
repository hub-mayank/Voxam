import type { ButtonHTMLAttributes } from 'react'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'primary' | 'danger'
}

function Button({ variant = 'default', className = '', type = 'button', ...rest }: Props) {
  const v = variant === 'default' ? '' : ` ${variant}`
  return <button type={type} className={`btn${v} ${className}`.trim()} {...rest} />
}

export default Button
