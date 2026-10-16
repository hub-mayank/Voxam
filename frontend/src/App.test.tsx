import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import App from './App'

beforeEach(() => window.history.replaceState({}, '', '/'))
afterEach(cleanup)

describe('application home and shared header', () => {
  it('introduces the product and gives students and faculty clear destinations', () => {
    render(<App />)

    expect(screen.getByRole('link', { name: 'Voxam' }).getAttribute('href')).toBe('/')
    expect(screen.getByRole('heading', { name: 'A fair, voice-first viva that your faculty can audit.' })).toBeTruthy()
    expect(screen.getByRole('link', { name: /I am taking a viva/ }).getAttribute('href')).toBe('/student')
    expect(screen.getByRole('link', { name: /Faculty dashboard/ }).getAttribute('href')).toBe('/faculty')
    expect(screen.getByText('It asks follow-up questions.')).toBeTruthy()
    expect(screen.getByText('It marks against a fixed rubric.')).toBeTruthy()
    expect(screen.getByText('Every mark has a transcript and audio to check.')).toBeTruthy()
  })

  it('shows the student section label after following the student destination', () => {
    render(<App />)

    fireEvent.click(screen.getByRole('link', { name: /I am taking a viva/ }))

    expect(screen.getByText('Viva')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Join your viva' })).toBeTruthy()
  })
})
