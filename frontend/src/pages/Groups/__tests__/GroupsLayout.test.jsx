import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi } from 'vitest'
import GroupsLayout from '../GroupsLayout'

const mockUseAuth = vi.fn()

vi.mock('../../../auth', () => ({
  useAuth: mockUseAuth,
}))

describe('GroupsLayout access gating', () => {
  beforeEach(() => {
    mockUseAuth.mockReset()
  })

  it('renders upgrade gate for non-premium users', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 1, username: 'reader', role: 'user', subscriptionTier: 'free' },
      loading: false,
    })

    render(
      <MemoryRouter initialEntries={['/groups']}>
        <Routes>
          <Route path="/groups" element={<GroupsLayout />}>
            <Route index element={<div>child route</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByTestId('groups-access-gate')).toBeInTheDocument()
    expect(screen.queryByText('child route')).not.toBeInTheDocument()
  })

  it('renders child routes when user has group access', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 2, username: 'premium', role: 'user', subscriptionTier: 'plus' },
      loading: false,
    })

    render(
      <MemoryRouter initialEntries={['/groups']}>
        <Routes>
          <Route path="/groups" element={<GroupsLayout />}>
            <Route index element={<div>child route</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByTestId('groups-layout')).toBeInTheDocument()
    expect(screen.getByText('child route')).toBeInTheDocument()
  })
})