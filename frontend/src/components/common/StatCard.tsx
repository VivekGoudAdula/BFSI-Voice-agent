interface StatCardProps {
  label: string
  value: string | number
  accent?: string
}

export function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <div className="stat-card" style={accent ? { borderTopColor: accent } : undefined}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  )
}
