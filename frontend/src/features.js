const normalizeValue = (value) => {
  if (!value) return null
  if (typeof value === 'string') return value.trim().toLowerCase()
  return null
}

export function getSubscriptionTier(user) {
  if (!user) return 'free'
  const tierSources = [
    user.subscriptionTier,
    user.subscription_tier,
    user.membershipTier,
    user.membership_tier,
    user.plan,
    user.tier,
  ]
  for (const value of tierSources) {
    const normalized = normalizeValue(value)
    if (normalized) return normalized
  }
  return 'free'
}

export function hasGroupAccess(user) {
  return !!user
}