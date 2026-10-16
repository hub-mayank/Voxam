import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import Page from './Page'

afterEach(cleanup)

describe('Page width', () => {
  it('uses the student-width layout by default', () => {
    render(<Page title="Student page">Content</Page>)
    expect(screen.getByRole('main').className).toBe('page')
  })

  it('supports the wide faculty layout', () => {
    render(<Page title="Faculty page" wide>Content</Page>)
    expect(screen.getByRole('main').className).toBe('page wide')
  })
})
