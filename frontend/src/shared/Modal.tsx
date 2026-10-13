import type { ReactNode } from 'react'
import Button from './Button'

function Modal({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal">
        <h2>{title}</h2>
        {children}
        <p>
          <Button onClick={onClose}>Close</Button>
        </p>
      </div>
    </div>
  )
}

export default Modal
