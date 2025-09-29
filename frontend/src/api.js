import axios from 'axios'

const api = axios.create({ baseURL: '/api', withCredentials: true })

let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    return Promise.reject(error)
  }
)

export async function listSnippets(params = {}) {
  const query = new URLSearchParams()
  if (params.q) {
    query.set('q', params.q)
  }
  if (Array.isArray(params.tags)) {
    params.tags
      .map((tag) => (tag || '').trim())
      .filter(Boolean)
      .forEach((tag) => {
        query.append('tag', tag)
      })
  }
  if (params.sort) {
    query.set('sort', params.sort)
  }
  if (params.limit) {
    query.set('limit', params.limit)
  }
  if (params.page) {
    query.set('page', params.page)
  }
  const config = {}
  if ([...query.keys()].length > 0) {
    config.params = query
  }
  const { data } = await api.get('/snippets', config)
  return data
}

export async function searchSnippets(params = {}) {
  const query = new URLSearchParams()
  if (params.q) {
    query.set('q', params.q)
  }
  if (Array.isArray(params.tags)) {
    params.tags
      .map((tag) => (tag || '').trim())
      .filter(Boolean)
      .forEach((tag) => {
        query.append('tag', tag)
      })
  }
  if (params.book) {
    query.set('book', params.book)
  }
  if (params.createdFrom) {
    query.set('createdFrom', params.createdFrom)
  }
  if (params.createdTo) {
    query.set('createdTo', params.createdTo)
  }
  if (params.limit) {
    query.set('limit', params.limit)
  }
  if (params.page) {
    query.set('page', params.page)
  }
  const config = {}
  if ([...query.keys()].length > 0) {
    config.params = query
  }
  const { data } = await api.get('/search/snippets', config)
  return data
}

export async function listSavedSearches() {
  const { data } = await api.get('/search/saved')
  return data
}

export async function getSavedSearch(savedSearchId) {
  const { data } = await api.get(`/search/saved/${savedSearchId}`)
  return data
}

export async function createSavedSearch(payload) {
  const { data } = await api.post('/search/saved', payload)
  return data
}

export async function updateSavedSearch(id, payload) {
  const { data } = await api.put(`/search/saved/${id}`, payload)
  return data
}

export async function deleteSavedSearch(id) {
  await api.delete(`/search/saved/${id}`)
}

export async function getEngagementStatus(params = {}) {
  const query = {}
  if (params.timezone) {
    query.timezone = params.timezone
  }
  const { data } = await api.get('/engagement/status', { params: query })
  return data
}

export async function createSnippet(payload) {
  const { data } = await api.post('/snippets', payload)
  return data
}

export async function getSnippet(id) {
  const { data } = await api.get(`/snippets/${id}`)
  return data
}

export async function updateSnippet(id, payload) {
  const { data } = await api.patch(`/snippets/${id}`, payload)
  return data
}

export async function getTrendingSnippets(params = {}) {
  const query = {}
  if (params.limit) query.limit = params.limit
  const { data } = await api.get('/snippets/trending', { params: query })
  return data
}

export async function listBooks(params = {}) {
  const query = {}
  if (params.limit) query.limit = params.limit
  if (params.q) query.q = params.q
  const { data } = await api.get('/books', { params: query })
  return data
}

export async function listTags(params = {}) {
  const query = {}
  if (params.limit) query.limit = params.limit
  const { data } = await api.get('/tags', { params: query })
  return data
}

export async function listPopularTags(params = {}) {
  const query = {}
  if (params.limit) query.limit = params.limit
  if (params.days) query.days = params.days
  const { data } = await api.get('/tags/popular', { params: query })
  return data
}

export async function deleteSnippet(id) {
  const { data } = await api.delete(`/snippets/${id}`)
  return data
}

export async function listSnippetComments(snippetId) {
  const { data } = await api.get(`/snippets/${snippetId}/comments`)
  return data
}

export async function createSnippetComment(snippetId, payload) {
  const { data } = await api.post(`/snippets/${snippetId}/comments`, payload)
  return data
}

export async function updateComment(commentId, payload) {
  const { data } = await api.patch(`/comments/${commentId}`, payload)
  return data
}

export async function deleteComment(commentId) {
  const { data } = await api.delete(`/comments/${commentId}`)
  return data
}

export async function voteComment(commentId, payload) {
  const { data } = await api.post(`/comments/${commentId}/vote`, payload)
  return data
}

export async function reportSnippet(snippetId, payload) {
  const { data } = await api.post(`/snippets/${snippetId}/report`, payload)
  return data
}

export async function reportComment(commentId, payload) {
  const { data } = await api.post(`/comments/${commentId}/report`, payload)
  return data
}

export async function listModerationReports() {
  const { data } = await api.get('/moderation/reports')
  return data
}

export async function resolveModerationReport(reportId, payload) {
  const { data } = await api.post(`/moderation/reports/${reportId}/resolve`, payload)
  return data
}

export async function listNotifications(params = {}, config = {}) {
  const query = {}
  if (params.limit) query.limit = params.limit
  if (params.cursor) query.cursor = params.cursor
  const requestConfig = { ...config }
  if (Object.keys(query).length > 0) {
    requestConfig.params = query
  }
  const { data } = await api.get('/notifications', requestConfig)
  return data
}

export async function markNotificationsRead(ids) {
  const payload = { ids }
  const { data } = await api.post('/notifications/mark_read', payload)
  return data
}

export async function getNotificationPreferences() {
  const { data } = await api.get('/users/me/notification_prefs')
  return data
}

export async function updateNotificationPreferences(payload) {
  const { data } = await api.put('/users/me/notification_prefs', payload)
  return data
}

export async function startDirectMessage(payload) {
  const { data } = await api.post('/dm/start', payload)
  return data
}

export async function listDirectMessageThreads() {
  const { data } = await api.get('/dm/threads')
  return data
}

export async function listDirectMessageThreadMessages(threadId, params = {}) {
  const query = {}
  if (params.cursor) query.cursor = params.cursor
  if (params.limit) query.limit = params.limit
  const { data } = await api.get(`/dm/threads/${threadId}/messages`, { params: query })
  return data
}

export async function sendDirectMessage(threadId, payload) {
  const { data } = await api.post(`/dm/threads/${threadId}/messages`, payload)
  return data
}

export async function markDirectMessageThreadRead(threadId) {
  const { data } = await api.post(`/dm/threads/${threadId}/read`)
  return data
}

const GROUP_DISCOVERY_RETRY_STATUSES = new Set([400, 404, 422])

function buildGroupDiscoveryQuery(params, { visibilityEncoding = 'repeat' } = {}) {
  const query = new URLSearchParams()

  if (params.q) {
    query.set('q', params.q)
  }

  const visibilityValues = (() => {
    if (!params.visibility) {
      return []
    }
    const raw = Array.isArray(params.visibility)
      ? params.visibility
      : String(params.visibility)
          .split(',')
          .map((value) => value.trim())
    const deduped = []
    raw.forEach((value) => {
      const normalized = (value || '').trim()
      if (normalized && !deduped.includes(normalized)) {
        deduped.push(normalized)
      }
    })
    return deduped
  })()

  if (visibilityValues.length > 0) {
    if (visibilityEncoding === 'comma') {
      query.set('visibility', visibilityValues.join(','))
    } else {
      visibilityValues.forEach((value) => {
        query.append('visibility', value)
      })
    }
  }

  if (params.limit) {
    query.set('limit', params.limit)
  }
  if (params.page) {
    query.set('page', params.page)
  }

  return query
}

async function requestGroupDiscovery(endpoint, query) {
  const config = [...query.keys()].length > 0 ? { params: query } : undefined
  const { data } = await api.get(endpoint, config)
  return data
}

export async function discoverGroups(params = {}) {
  const attempts = [
    { endpoint: '/groups', visibilityEncoding: 'repeat' },
    { endpoint: '/groups', visibilityEncoding: 'comma' },
    { endpoint: '/groups/discover', visibilityEncoding: 'repeat' },
    { endpoint: '/groups/discover', visibilityEncoding: 'comma' },
  ]

  let lastError = null

  for (const attempt of attempts) {
    const query = buildGroupDiscoveryQuery(params, { visibilityEncoding: attempt.visibilityEncoding })
    try {
      return await requestGroupDiscovery(attempt.endpoint, query)
    } catch (error) {
      const status = error?.response?.status
      lastError = error
      if (!GROUP_DISCOVERY_RETRY_STATUSES.has(status)) {
        throw error
      }
    }
  }

  if (lastError) {
    throw lastError
  }

  return []
}

export async function getGroup(groupId) {
  const { data } = await api.get(`/groups/${groupId}`)
  return data
}

export async function getGroupBySlug(slug) {
  const { data } = await api.get(`/groups/slug/${slug}`)
  return data
}

export async function listMyGroupMemberships() {
  try {
    const { data } = await api.get('/groups/memberships')
    return data
  } catch (err) {
    if (err?.response?.status === 404) {
      // Some API versions expose the collection under /groups/me
      const { data } = await api.get('/groups/me')
      return data
    }
    throw err
  }
}

export async function listGroupMembers(groupId) {
  const { data } = await api.get(`/groups/${groupId}/members`)
  return data
}

export async function listGroupSnippets(groupId, params = {}) {
  const query = {}
  if (params.limit) query.limit = params.limit
  if (params.page) query.page = params.page
  const { data } = await api.get(`/groups/${groupId}/snippets`, { params: query })
  return data
}

export async function joinGroup(groupId) {
  const { data } = await api.post(`/groups/${groupId}/join`)
  return data
}

export async function updateGroupMember(groupId, userId, payload) {
  const { data } = await api.put(`/groups/${groupId}/members/${userId}`, payload)
  return data
}

export async function removeGroupMember(groupId, userId) {
  const { data } = await api.delete(`/groups/${groupId}/members/${userId}`)
  return data
}

export async function listGroupInvites(groupId, params = {}) {
  const query = {}
  if (params.status) query.status = params.status
  if (params.limit) query.limit = params.limit
  const { data } = await api.get(`/groups/${groupId}/invites`, { params: query })
  return data
}

export async function createGroupInvite(groupId, payload) {
  const { data } = await api.post(`/groups/${groupId}/invites`, payload)
  return data
}

export async function acceptGroupInvite(inviteCode) {
  const { data } = await api.post(`/groups/invites/${inviteCode}/accept`)
  return data
}

export async function getUnreadNotificationCount({ signal } = {}) {
  const config = {}
  if (signal) {
    config.signal = signal
  }
  const { data } = await api.get('/notifications/unread_count', config)
  return data
}

export async function register(payload) {
  const { data } = await api.post('/auth/register', payload)
  return data
}

export async function requestPasswordReset(payload) {
  const { data } = await api.post('/auth/password-reset', payload)
  return data
}

export async function login(credentials) {
  const { data } = await api.post('/auth/login', credentials)
  return data
}

export async function logout() {
  await api.post('/auth/logout')
}

export async function fetchCurrentUser() {
  const { data } = await api.get('/auth/me')
  return data
}

export default api