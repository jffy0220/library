const PREMIUM_GROUP_TIERS = new Set(['plus', 'pro', 'premium', 'enterprise'])

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
  if (!user) return false
  const siteRole = normalizeValue(user.role)
  if (siteRole && (siteRole === 'moderator' || siteRole === 'admin')) {
    return true
  }
  const entitlements = user.entitlements || user.features || user.featureFlags || {}
  if (typeof entitlements === 'object') {
    const directFlag = entitlements.groups ?? entitlements.groupAccess
    if (directFlag === true) return true
  }
  const tier = getSubscriptionTier(user)
  return PREMIUM_GROUP_TIERS.has(tier)
}