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

  it('renders sign-in gate when no user is present', () => {
    mockUseAuth.mockReturnValue({
      user: null,
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

  it('renders child routes when a user is signed in', () => {
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