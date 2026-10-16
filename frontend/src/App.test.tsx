import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import App from './App'

beforeEach(() => window.history.replaceState({}, '', '/'))
afterEach(cleanup)

describe('application home and shared header', () => {
  it('introduces the product and gives students and faculty clear destinations', () => {
    render(<App />)

    expect(screen.getByRole('link', { name: 'Voxam' }).getAttribute('href')).toBe('/')
    expect(screen.getByRole('heading', { name: 'A thoughtful viva. A fairer way to show what you know.' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /I am taking a viva/ }).getAttribute('href')).toBe('/student')
    expect(screen.getByRole('link', { name: /Faculty dashboard/ }).getAttribute('href')).toBe('/faculty')
    expect(screen.getByText('Follow-up questions keep each conversation focused.')).toBeTruthy()
    expect(screen.getByText('One shared rubric makes marking consistent.')).toBeTruthy()
    expect(screen.getByText('Transcript and audio let faculty review each mark.')).toBeTruthy()
  })

  it('shows the student section label after following the student destination', () => {
    render(<App />)

    fireEvent.click(screen.getByRole('link', { name: /I am taking a viva/ }))

    expect(screen.getByRole('banner').querySelector('.site-section')?.textContent).toBe('Viva')
    expect(screen.getByRole('heading', { name: 'Join your viva' })).toBeTruthy()
  })

  it('switches themes and persists the selected theme', () => {
    render(<App />)

    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))

    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('voxam.theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeTruthy()
  })
})
