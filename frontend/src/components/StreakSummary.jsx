import React from 'react'

function formatDate(dateValue) {
  if (!dateValue) return null
  try {
    const date = new Date(dateValue)
    if (Number.isNaN(date.getTime())) return null
    return date.toLocaleDateString()
  } catch (err) {
    return null
  }
}

export default function StreakSummary({ streak }) {
  if (!streak) return null
  const current = Number.isFinite(streak.current) ? streak.current : 0
  const longest = Number.isFinite(streak.longest) ? streak.longest : 0
  const activeToday = Boolean(streak.activeToday)
  const badge = streak.currentBadge
  const nextBadge = streak.nextBadge
  const timezone = streak.timezone || 'UTC'
  const lastActiveLabel = formatDate(streak.lastActiveDate)

  return (
    <div className="streak-card card shadow-sm">
      <div className="card-body d-flex align-items-center gap-3">
        <div className="streak-card__icon" aria-hidden="true">
          {badge?.icon || '📚'}
        </div>
        <div className="flex-grow-1">
          <div className="d-flex flex-column flex-sm-row justify-content-between align-items-sm-center gap-2">
            <div>
              <h2 className="h5 mb-1">Daily streak</h2>
              <p className="mb-0 text-body-secondary">
                {current === 0 ? 'Start a new habit today.' : `You're on a ${current}-day streak.`}
              </p>
            </div>
            <div className="streak-card__count">
              <span className="streak-card__count-number">{current}</span>
              <span className="streak-card__count-label">days</span>
            </div>
          </div>
          <div className="d-flex flex-wrap gap-3 mt-3 streak-card__details">
            {badge ? (
              <div className="streak-card__badge" title={badge.description || badge.name}>
                <span className="streak-card__badge-icon" aria-hidden="true">{badge.icon}</span>
                <span className="streak-card__badge-text">{badge.name}</span>
              </div>
            ) : null}
            <div className="text-body-secondary streak-card__detail">Longest streak: {longest} days</div>
            {nextBadge ? (
              <div className="text-body-secondary streak-card__detail">
                Next badge at {nextBadge.threshold} days ({nextBadge.icon})
              </div>
            ) : null}
            {lastActiveLabel ? (
              <div className="text-body-secondary streak-card__detail">Last capture: {lastActiveLabel}</div>
            ) : null}
            <div className="text-body-tertiary streak-card__detail">Timezone: {timezone}</div>
          </div>
        </div>
      </div>
      {!activeToday ? (
        <div className="card-footer bg-body-tertiary text-body-secondary py-2">
          Add a new insight before midnight to extend your streak.
        </div>
      ) : null}
    </div>
  )
}