import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { vi } from 'vitest'
import GroupInviteAccept from '../GroupInviteAccept'

const mockAcceptInvite = vi.fn()

vi.mock('../../../api', () => ({
  acceptGroupInvite: mockAcceptInvite,
}))

describe('GroupInviteAccept', () => {
  beforeEach(() => {
    mockAcceptInvite.mockReset()
  })

  it('accepts an invite and shows a success message', async () => {
    mockAcceptInvite.mockResolvedValue({ member: { role: 'member' } })
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/groups/invite/TEST-CODE']}>
        <Routes>
          <Route path="/groups/invite/:inviteCode" element={<GroupInviteAccept />} />
        </Routes>
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: /accept invite/i }))

    expect(mockAcceptInvite).toHaveBeenCalledWith('TEST-CODE')
    expect(await screen.findByText(/Invite accepted!/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /View my groups/i })).toBeInTheDocument()
  })

  it('shows an error when invite acceptance fails', async () => {
    mockAcceptInvite.mockRejectedValue({ response: { data: { detail: 'Invite expired' } } })
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/groups/invite/BAD-CODE']}>
        <Routes>
          <Route path="/groups/invite/:inviteCode" element={<GroupInviteAccept />} />
        </Routes>
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: /accept invite/i }))

    expect(mockAcceptInvite).toHaveBeenCalledWith('BAD-CODE')
    expect(await screen.findByText(/Invite expired/i)).toBeInTheDocument()
  })
})