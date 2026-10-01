import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart as RechartsRadarChart,
  ResponsiveContainer,
} from 'recharts'
import type { DimensionScore } from '../types'

interface RadarChartProps {
  dimensions: DimensionScore[]
}

export default function RadarChart({ dimensions }: RadarChartProps) {
  const data = dimensions.map((item) => ({
    subject: item.label,
    score: item.score,
    fullMark: 100,
  }))

  return (
    <div className="radar-chart" role="img" aria-label={`四维雷达图，${dimensions.map((item) => `${item.label} ${item.score} 分`).join('，')}`}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartsRadarChart cx="50%" cy="50%" outerRadius="76%" data={data}>
          <PolarGrid stroke="rgba(29, 29, 31, 0.16)" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: '#1d1d1f', fontSize: 13 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar dataKey="score" stroke="#3478f6" fill="#3478f6" fillOpacity={0.22} strokeWidth={2} />
        </RechartsRadarChart>
      </ResponsiveContainer>
    </div>
  )
}
